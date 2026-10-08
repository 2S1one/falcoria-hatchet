"""Turns one IPChangedEvent into chain launches, per rules A/B/C."""

from collections.abc import Awaitable, Callable, Iterator
from itertools import chain
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_contracts.httpx import HttpxTarget
from asm_core.scanledger_bridge.events import IPChangedEvent, PortProtocol
from asm_core.scanledger_bridge.models import ScanledgerBridgeSeenTargetDB

# HttpxTarget.target_id is caller-assigned and unused past echoing the result back; the bridge has no
# caller-side int-id system, so every target gets the same placeholder.
_TARGET_ID_PLACEHOLDER = 0


def _derive_targets(event: IPChangedEvent) -> Iterator[tuple[str | None, int]]:
    """Yields (hostname, port) pairs per rules A/B/C; hostname is None for a bare-IP target."""
    hostnames: list[str | None] = list(event.hostnames.current) or [None]

    def rule_a() -> Iterator[tuple[str | None, int]]:
        for port in event.ports.added:
            if port.protocol is not PortProtocol.TCP:
                continue
            for hostname in hostnames:
                yield hostname, port.number

    def rule_b() -> Iterator[tuple[str | None, int]]:
        for hostname in event.hostnames.added:
            for port in event.ports.current:
                if port.protocol is not PortProtocol.TCP:
                    continue
                yield hostname, port.number

    def rule_c() -> Iterator[tuple[str | None, int]]:
        for change in event.service_changes:
            if change.protocol is not PortProtocol.TCP:
                continue
            for hostname in hostnames:
                yield hostname, change.number

    return chain(rule_a(), rule_b(), rule_c())


async def _mark_seen(
    session: AsyncSession, project_id: UUID, scan_id: UUID, target: str, port: int
) -> bool:
    """Inserts the dedup row; returns True only if this target hadn't been seen for this scan yet."""
    stmt = (
        pg_insert(ScanledgerBridgeSeenTargetDB)
        .values(
            project_id=project_id,
            scan_id=scan_id,
            target=target,
            port=port,
            protocol=PortProtocol.TCP.value,
        )
        .on_conflict_do_nothing(
            index_elements=["project_id", "scan_id", "target", "port", "protocol"]
        )
        .returning(col(ScanledgerBridgeSeenTargetDB.target))
    )
    connection = await session.connection()
    result = await connection.execute(stmt)
    return result.first() is not None


async def handle_event(
    sessionmaker: async_sessionmaker[AsyncSession],
    event: IPChangedEvent,
    launch: Callable[[HttpxThenNucleiTask], Awaitable[None]],
) -> None:
    """Derives this event's targets and launches the chain for each one not already seen.

    Skips entirely when `scan_id` is null (manual upload — settled, not scan-triggering). Each target
    gets its own session and transaction. The launch runs before the commit of its dedup row: if the
    launch fails, the row is rolled back and the exception reaches the caller, so the next poll retries
    that target; if the commit fails after a launch, the target may be launched twice.
    """
    if event.scan_id is None:
        return
    for hostname, port in _derive_targets(event):
        target = hostname or event.ip
        async with sessionmaker() as session:
            if await _mark_seen(session, event.project_id, event.scan_id, target, port):
                await launch(
                    HttpxThenNucleiTask(
                        project_id=event.project_id,
                        scan_id=event.scan_id,
                        target=HttpxTarget(
                            target_id=_TARGET_ID_PLACEHOLDER,
                            ip=event.ip,
                            hostname=hostname,
                            port=port,
                        ),
                    )
                )
            await session.commit()
