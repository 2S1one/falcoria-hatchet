import logging
from typing import Final

from asm_logging import configure_logging
from asm_nuclei_worker.tasks import hatchet, nuclei_scan

logger = logging.getLogger(__name__)

WORKER_NAME: Final = "nuclei-worker"
# One batch at a time per worker: a nuclei process uses the machine's network bandwidth.
WORKER_SLOTS: Final = 1


def main() -> None:
    """Runs the nuclei worker until the process is stopped."""
    configure_logging()
    logger.info("starting %s", WORKER_NAME)
    hatchet.worker(WORKER_NAME, slots=WORKER_SLOTS, workflows=[nuclei_scan]).start()


if __name__ == "__main__":
    main()
