"""Background poller: drains scanledger's event feed into the adapter, forever."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_core.config import get_scanledger_settings
from asm_core.constants import SCANLEDGER_POLL_INTERVAL_SEC
from asm_core.db.database import get_sessionmaker
from asm_core.scanledger_bridge.adapter import handle_event
from asm_core.scanledger_bridge.events import EventPage, Project
from asm_core.scanledger_bridge.models import ScanledgerBridgeCursorDB

logger = logging.getLogger(__name__)

_DEFAULT_CURSOR = "0.0"

Launch = Callable[[HttpxThenNucleiTask], Awaitable[None]]


async def _list_project_ids(client: httpx.AsyncClient) -> list[UUID]:
    """Lists every project visible to the configured token."""
    response = await client.get("/projects")
    response.raise_for_status()
    return [Project.model_validate(item).id for item in response.json()]


async def _get_cursor(sessionmaker: async_sessionmaker[AsyncSession], project_id: UUID) -> str:
    async with sessionmaker() as session:
        row = await session.get(ScanledgerBridgeCursorDB, project_id)
        return row.cursor if row is not None else _DEFAULT_CURSOR


async def _save_cursor(
    sessionmaker: async_sessionmaker[AsyncSession], project_id: UUID, cursor: str
) -> None:
    async with sessionmaker() as session:
        await session.merge(
            ScanledgerBridgeCursorDB(
                project_id=project_id, cursor=cursor, updated_at=datetime.now(UTC)
            )
        )
        await session.commit()


async def _drain_project(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    project_id: UUID,
    launch: Launch,
) -> None:
    """Pages through this project's event feed until `next_cursor` stops advancing."""
    cursor = await _get_cursor(sessionmaker, project_id)
    while True:
        response = await client.get(f"/projects/{project_id}/events", params={"after": cursor})
        response.raise_for_status()
        page = EventPage.model_validate(response.json())
        for event in page.items:
            await handle_event(sessionmaker, event, launch)
        if page.next_cursor == cursor:
            return
        cursor = page.next_cursor
        await _save_cursor(sessionmaker, project_id, cursor)


async def run_poller(launch: Launch) -> None:
    """Polls every project for new events, forever, until cancelled.

    Each project is drained fully (every backlogged page) before moving to the next, so a project
    that fell behind catches up without waiting for a full round of every other project first.
    """
    settings = get_scanledger_settings()
    sessionmaker = get_sessionmaker()
    headers = {"Authorization": f"Bearer {settings.asm_token.get_secret_value()}"}
    # keepalive_expiry well under SCANLEDGER_POLL_INTERVAL_SEC's 5s, so httpx drops an idle
    # connection itself before the next poll could race the server's own idle-connection close.
    async with httpx.AsyncClient(
        base_url=settings.api_url, headers=headers, limits=httpx.Limits(keepalive_expiry=1.0)
    ) as client:
        while True:
            try:
                for project_id in await _list_project_ids(client):
                    await _drain_project(client, sessionmaker, project_id, launch)
            except Exception:  # top-level handler: one failed poll must not stop the next one
                logger.exception("scanledger bridge poll iteration failed, retrying")
            await asyncio.sleep(SCANLEDGER_POLL_INTERVAL_SEC)
