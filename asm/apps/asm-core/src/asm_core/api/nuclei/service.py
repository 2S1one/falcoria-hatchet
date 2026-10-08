"""Reads of stored nuclei findings."""

import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_core.api.nuclei.schemas import NucleiFindingOut
from asm_core.db.models import NucleiFindingCurrentDB


async def list_findings(session: AsyncSession, project_id: uuid.UUID) -> list[NucleiFindingOut]:
    """Returns every currently-active finding for `project_id`."""
    rows = (
        await session.exec(
            select(NucleiFindingCurrentDB).where(NucleiFindingCurrentDB.project_id == project_id)
        )
    ).all()
    return [NucleiFindingOut.model_validate(row, from_attributes=True) for row in rows]
