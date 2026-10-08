import uuid

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_core.db.database import get_sessionmaker
from asm_core.scanledger_bridge.events import (
    EventPage,
    HostnameDelta,
    IPChangedEvent,
    PortDelta,
    PortProtocol,
    PortRef,
)
from asm_core.scanledger_bridge.models import ScanledgerBridgeCursorDB
from asm_core.scanledger_bridge.poller import _drain_project

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _event(ip: str) -> IPChangedEvent:
    return IPChangedEvent(
        event_id=uuid.uuid4(),
        project_id=_PROJECT,
        ip=ip,
        scan_id=_SCAN,
        hostnames=HostnameDelta(current=[], added=[]),
        ports=PortDelta(current=[], added=[PortRef(number=80, protocol=PortProtocol.TCP)]),
    )


def _feed(pages: dict[str, EventPage]) -> httpx.AsyncClient:
    """A scanledger stand-in that serves `pages` keyed by the `after` cursor."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = pages[request.url.params["after"]]
        return httpx.Response(200, json=page.model_dump(mode="json"))

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://scanledger.test"
    )


class _Launcher:
    def __init__(self) -> None:
        self.launched: list[HttpxThenNucleiTask] = []

    async def __call__(self, task: HttpxThenNucleiTask) -> None:
        self.launched.append(task)


async def test_every_page_is_processed_and_the_cursor_is_saved(session: AsyncSession) -> None:
    pages = {
        "0.0": EventPage(items=[_event("192.0.2.1")], next_cursor="1.1"),
        "1.1": EventPage(items=[_event("192.0.2.2")], next_cursor="2.2"),
        "2.2": EventPage(items=[], next_cursor="2.2"),
    }
    launcher = _Launcher()

    async with _feed(pages) as client:
        await _drain_project(client, get_sessionmaker(), _PROJECT, launcher)

    assert [task.target.ip for task in launcher.launched] == ["192.0.2.1", "192.0.2.2"]
    row = await session.get(ScanledgerBridgeCursorDB, _PROJECT)
    assert row is not None
    assert row.cursor == "2.2"


async def test_a_second_poll_starts_from_the_saved_cursor(session: AsyncSession) -> None:
    first = {
        "0.0": EventPage(items=[_event("192.0.2.1")], next_cursor="1.1"),
        "1.1": EventPage(items=[], next_cursor="1.1"),
    }
    second = {
        "1.1": EventPage(items=[_event("192.0.2.9")], next_cursor="2.2"),
        "2.2": EventPage(items=[], next_cursor="2.2"),
    }
    launcher = _Launcher()

    async with _feed(first) as client:
        await _drain_project(client, get_sessionmaker(), _PROJECT, launcher)
    async with _feed(second) as client:
        await _drain_project(client, get_sessionmaker(), _PROJECT, launcher)

    assert [task.target.ip for task in launcher.launched] == ["192.0.2.1", "192.0.2.9"]
