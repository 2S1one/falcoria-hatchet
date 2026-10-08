import asyncio
import logging
from typing import Final

from asm_core.constants import CHAIN_WORKER_SLOTS
from asm_core.db.database import create_db_and_tables, dispose_engine
from asm_core.tasks import (
    hatchet,
    httpx_scan_and_store,
    httpx_then_nuclei,
    persist_nuclei_findings,
)
from asm_logging import configure_logging

logger = logging.getLogger(__name__)

WORKER_NAME: Final = "asm-core-worker"


async def _prepare_database() -> None:
    """Creates the tables, then drops the pool so the worker's own event loop opens fresh connections."""
    await create_db_and_tables()
    await dispose_engine()


def main() -> None:
    """Runs the asm-core worker until the process is stopped."""
    configure_logging()
    asyncio.run(_prepare_database())
    logger.info("starting %s", WORKER_NAME)
    hatchet.worker(
        WORKER_NAME,
        slots=CHAIN_WORKER_SLOTS,
        workflows=[httpx_then_nuclei, httpx_scan_and_store, persist_nuclei_findings],
    ).start()


if __name__ == "__main__":
    main()
