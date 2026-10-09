"""FastAPI entrypoint: run as `uvicorn asm_core.app:fastapi_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from asm_core.api.httpx.router import router as httpx_router
from asm_core.api.nuclei.router import router as nuclei_router
from asm_core.api.scanledger_access import dispose_scanledger_access_client
from asm_core.db.database import create_db_and_tables, dispose_engine


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Creates the tables on start; closes the scanledger client and database pool on shutdown."""
    await create_db_and_tables()
    try:
        yield
    finally:
        await dispose_scanledger_access_client()
        await dispose_engine()


def create_app() -> FastAPI:
    """Builds the FastAPI app, wiring in every scanner's router."""
    app = FastAPI(title="asm-core", lifespan=_lifespan)
    app.include_router(nuclei_router)
    app.include_router(httpx_router)
    return app


fastapi_app = create_app()
