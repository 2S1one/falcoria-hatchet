"""Async database engine, session factory and schema creation."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_core.config import get_db_settings
from asm_core.db.models import HttpxResultCurrentDB, NucleiFindingCurrentDB
from asm_core.scanledger_bridge.models import ScanledgerBridgeCursorDB, ScanledgerBridgeSeenTargetDB


def _database_url() -> URL:
    """Builds the asyncpg connection URL from settings, escaping credentials safely."""
    s = get_db_settings()
    return URL.create(
        drivername="postgresql+asyncpg",
        username=s.user,
        password=s.password.get_secret_value(),
        host=s.host,
        port=s.port,
        database=s.name,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    """Returns the process-wide async engine, created on first use."""
    return create_async_engine(_database_url(), echo=get_db_settings().echo, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Returns the process-wide session factory bound to the engine."""
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def dispose_engine() -> None:
    """Disposes the engine's connection pool; called on shutdown."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


async def create_db_and_tables() -> None:
    """Creates this service's tables if they do not exist.

    Stand-in until migrations land: no upgrade or downgrade path, and a changed column is not applied
    to an existing table.
    """
    tables = [
        NucleiFindingCurrentDB.__table__,  # pyright: ignore[reportAttributeAccessIssue]
        HttpxResultCurrentDB.__table__,  # pyright: ignore[reportAttributeAccessIssue]
        ScanledgerBridgeCursorDB.__table__,  # pyright: ignore[reportAttributeAccessIssue]
        ScanledgerBridgeSeenTargetDB.__table__,  # pyright: ignore[reportAttributeAccessIssue]
    ]
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all, tables=tables)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yields a request-scoped session; commits on success, rolls back on any error.

    One unit of work per request. Services receive this session and never commit, roll back or close it.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
