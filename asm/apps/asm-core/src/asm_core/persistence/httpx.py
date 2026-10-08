"""Storage of the latest httpx probe per target."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.httpx import HttpxScanResult
from asm_core.db.models import HttpxResultCurrentDB

_CONFLICT_KEY = ["project_id", "target_ip", "target_port", "target_hostname", "target_path"]


async def save_httpx_result(
    session: AsyncSession, project_id: uuid.UUID, scan_id: uuid.UUID, result: HttpxScanResult
) -> None:
    """Stores this probe as the target's current httpx result.

    Inserts the row, or on a repeat probe of the same target refreshes `is_http`, `attempts` and the
    last_seen_* columns while keeping first_seen_*. Repeating the same call is harmless. Does not commit.
    """
    now = datetime.now(UTC)
    target = result.target
    statement = pg_insert(HttpxResultCurrentDB).values(
        project_id=project_id,
        target_ip=target.ip,
        target_port=target.port,
        target_hostname=target.hostname,
        target_path=target.path,
        is_http=result.is_http,
        attempts=[attempt.model_dump(mode="json") for attempt in result.attempts],
        first_seen_scan_id=scan_id,
        first_seen_at=now,
        last_seen_scan_id=scan_id,
        last_seen_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=_CONFLICT_KEY,
        set_={
            "is_http": statement.excluded.is_http,
            "attempts": statement.excluded.attempts,
            "last_seen_scan_id": statement.excluded.last_seen_scan_id,
            "last_seen_at": statement.excluded.last_seen_at,
        },
    )
    connection = await session.connection()
    await connection.execute(statement)
