import logging

from asm_httpx_worker.tasks import hatchet, httpx_scan
from asm_logging import configure_logging

logger = logging.getLogger(__name__)

WORKER_NAME = "httpx-worker"


def main() -> None:
    """Runs the httpx worker until the process is stopped."""
    configure_logging()
    logger.info("starting %s", WORKER_NAME)
    hatchet.worker(WORKER_NAME, workflows=[httpx_scan]).start()


if __name__ == "__main__":
    main()
