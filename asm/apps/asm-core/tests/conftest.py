import base64
import json
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_core.config import get_db_settings
from asm_core.db.database import (
    create_db_and_tables,
    dispose_engine,
    get_engine,
    get_sessionmaker,
)

_TEST_DB_NAME = "asm_core_test"


def _dummy_hatchet_token() -> str:
    """A structurally valid JWT: the SDK parses its token when the client is built, never contacts the engine."""

    def part(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {
        "aud": "test",
        "exp": 4102444800,
        "grpc_broadcast_address": "localhost:7077",
        "iss": "http://localhost:8080",
        "server_url": "http://localhost:8080",
        "sub": "00000000-0000-0000-0000-000000000000",
        "token_id": "00000000-0000-0000-0000-000000000000",
    }
    return ".".join([part({"alg": "HS256", "typ": "JWT"}), part(claims), "signature"])


# asm_core.tasks builds a Hatchet client when it is imported, which needs a token; a real one wins.
os.environ.setdefault("HATCHET_CLIENT_TOKEN", _dummy_hatchet_token())
os.environ.setdefault("HATCHET_CLIENT_TLS_STRATEGY", "none")
_TABLES = (
    "nuclei_findings_current, httpx_results_current, "
    "scanledger_bridge_seen_targets, scanledger_bridge_cursor"
)


@pytest.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    """A session on the empty asm_core_test database; skips when no database is configured."""
    if "ASM_CORE_DB_HOST" not in os.environ:
        pytest.skip("ASM_CORE_DB_* is not set")
    monkeypatch.setenv("ASM_CORE_DB_NAME", _TEST_DB_NAME)
    for cached in (get_db_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    await create_db_and_tables()
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY"))
    async with get_sessionmaker()() as db_session:
        yield db_session
    await dispose_engine()
    for cached in (get_db_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
