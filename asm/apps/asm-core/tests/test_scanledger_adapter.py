import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_core.db.database import get_sessionmaker
from asm_core.scanledger_bridge.adapter import _derive_targets, handle_event
from asm_core.scanledger_bridge.events import (
    HostnameDelta,
    IPChangedEvent,
    PortDelta,
    PortDetail,
    PortProtocol,
    PortRef,
    ServiceChange,
)
from asm_core.scanledger_bridge.models import ScanledgerBridgeSeenTargetDB

_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _event(
    hostnames_current: list[str] | None = None,
    hostnames_added: list[str] | None = None,
    ports_current: list[PortDetail] | None = None,
    ports_added: list[PortRef] | None = None,
    service_changes: list[ServiceChange] | None = None,
    scan_id: uuid.UUID | None = _SCAN_ID,
) -> IPChangedEvent:
    return IPChangedEvent(
        event_id=uuid.uuid4(),
        project_id=_PROJECT_ID,
        ip="1.2.3.4",
        scan_id=scan_id,
        hostnames=HostnameDelta(current=hostnames_current or [], added=hostnames_added or []),
        ports=PortDelta(current=ports_current or [], added=ports_added or []),
        service_changes=service_changes or [],
    )


def test_rule_a_new_port_times_current_hostnames() -> None:
    event = _event(
        hostnames_current=["shop.example.com", "cdn.example.com"],
        ports_added=[PortRef(number=8080, protocol=PortProtocol.TCP)],
    )
    assert set(_derive_targets(event)) == {
        ("shop.example.com", 8080),
        ("cdn.example.com", 8080),
    }


def test_rule_a_new_port_with_no_hostnames_yields_bare_ip_target() -> None:
    event = _event(ports_added=[PortRef(number=22, protocol=PortProtocol.TCP)])
    assert set(_derive_targets(event)) == {(None, 22)}


def test_rule_a_skips_udp_ports() -> None:
    event = _event(
        hostnames_current=["shop.example.com"],
        ports_added=[PortRef(number=53, protocol=PortProtocol.UDP)],
    )
    assert set(_derive_targets(event)) == set()


def test_rule_b_new_hostname_times_current_ports() -> None:
    event = _event(
        hostnames_added=["new.example.com"],
        ports_current=[
            PortDetail(number=80, protocol=PortProtocol.TCP),
            PortDetail(number=443, protocol=PortProtocol.TCP),
        ],
    )
    assert set(_derive_targets(event)) == {("new.example.com", 80), ("new.example.com", 443)}


def test_rule_b_skips_udp_ports() -> None:
    event = _event(
        hostnames_added=["new.example.com"],
        ports_current=[PortDetail(number=53, protocol=PortProtocol.UDP)],
    )
    assert set(_derive_targets(event)) == set()


def test_rule_c_service_change_times_current_hostnames() -> None:
    event = _event(
        hostnames_current=["shop.example.com"],
        service_changes=[ServiceChange(number=80, protocol=PortProtocol.TCP)],
    )
    assert set(_derive_targets(event)) == {("shop.example.com", 80)}


def test_rules_combine_within_one_event() -> None:
    event = _event(
        hostnames_current=["shop.example.com"],
        hostnames_added=["new.example.com"],
        ports_current=[PortDetail(number=443, protocol=PortProtocol.TCP)],
        ports_added=[PortRef(number=8080, protocol=PortProtocol.TCP)],
    )
    assert set(_derive_targets(event)) == {
        ("shop.example.com", 8080),  # rule A
        ("new.example.com", 443),  # rule B
    }


class _Launcher:
    def __init__(self, *, fail_on_port: int | None = None) -> None:
        self.launched: list[HttpxThenNucleiTask] = []
        self._fail_on_port = fail_on_port

    async def __call__(self, task: HttpxThenNucleiTask) -> None:
        if task.target.port == self._fail_on_port:
            raise RuntimeError("engine unavailable")
        self.launched.append(task)


async def _seen(session: AsyncSession) -> list[ScanledgerBridgeSeenTargetDB]:
    return list((await session.exec(select(ScanledgerBridgeSeenTargetDB))).all())


def _two_ports_event() -> IPChangedEvent:
    return _event(
        hostnames_current=["shop.example.com"],
        ports_added=[
            PortRef(number=80, protocol=PortProtocol.TCP),
            PortRef(number=8080, protocol=PortProtocol.TCP),
        ],
    )


@pytest.mark.anyio
@pytest.mark.postgres
async def test_each_target_is_launched_once_even_if_the_event_arrives_twice(
    session: AsyncSession,
) -> None:
    launcher = _Launcher()
    sessionmaker: async_sessionmaker[AsyncSession] = get_sessionmaker()
    event = _two_ports_event()

    await handle_event(sessionmaker, event, launcher)
    await handle_event(sessionmaker, event, launcher)

    assert sorted(task.target.port for task in launcher.launched) == [80, 8080]
    assert {task.target.hostname for task in launcher.launched} == {"shop.example.com"}
    assert len(await _seen(session)) == 2


@pytest.mark.anyio
@pytest.mark.postgres
async def test_an_event_without_a_scan_launches_nothing(session: AsyncSession) -> None:
    launcher = _Launcher()

    await handle_event(get_sessionmaker(), _event(scan_id=None), launcher)

    assert launcher.launched == []
    assert await _seen(session) == []


@pytest.mark.anyio
@pytest.mark.postgres
async def test_a_failed_launch_leaves_no_seen_row_so_the_retry_launches_it(
    session: AsyncSession,
) -> None:
    event = _two_ports_event()
    failing = _Launcher(fail_on_port=8080)

    with pytest.raises(RuntimeError):
        await handle_event(get_sessionmaker(), event, failing)

    assert [task.target.port for task in failing.launched] == [80]
    assert [row.port for row in await _seen(session)] == [80]

    retry = _Launcher()
    await handle_event(get_sessionmaker(), event, retry)

    assert [task.target.port for task in retry.launched] == [8080]
