import asyncio
import logging
import signal

from asm_core.db.database import create_db_and_tables, dispose_engine
from asm_core.scanledger_bridge.poller import run_poller
from asm_core.tasks import start_chain
from asm_logging import configure_logging

logger = logging.getLogger(__name__)


async def _run() -> None:
    """Polls scanledger until SIGINT or SIGTERM, then closes the database pool."""
    await create_db_and_tables()
    poller = asyncio.create_task(run_poller(start_chain))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, poller.cancel)
    try:
        await poller
    except asyncio.CancelledError:
        logger.info("scanledger bridge stopped")
    finally:
        await dispose_engine()


def main() -> None:
    """Runs the scanledger bridge until the process is stopped."""
    configure_logging()
    logger.info("starting scanledger bridge")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
