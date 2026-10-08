"""Reads of stored httpx results."""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_core.api.httpx.schemas import HttpxResultOut
from asm_core.db.models import HttpxResultCurrentDB


async def list_results(session: AsyncSession, project_id: uuid.UUID) -> list[HttpxResultOut]:
    """Returns the current httpx result of every target of `project_id`."""
    rows = (
        await session.exec(
            select(HttpxResultCurrentDB).where(HttpxResultCurrentDB.project_id == project_id)
        )
    ).all()
    return [HttpxResultOut.model_validate(row, from_attributes=True) for row in rows]
