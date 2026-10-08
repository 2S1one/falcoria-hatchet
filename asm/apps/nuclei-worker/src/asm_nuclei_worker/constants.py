from datetime import timedelta
from typing import Final

NUCLEI_BATCH_SIZE: Final = 25  # placeholder
NUCLEI_BATCH_INTERVAL: Final = timedelta(seconds=30)  # placeholder
# The engine reads this field from every call's input; calls with the same value share a batch.
NUCLEI_BATCH_GROUP_KEY: Final = "input.batch_key"
# The scan's own timeout (in the task) is the real limit; Hatchet's is only a far-away backstop.
NUCLEI_EXECUTION_TIMEOUT: Final = timedelta(days=3)
# A batch waits here for the worker's single slot while earlier scans run.
NUCLEI_SCHEDULE_TIMEOUT: Final = timedelta(days=7)
# The asm-core task that stores findings is idempotent, so a failed forward can be tried again.
NUCLEI_PERSIST_RETRIES: Final = 2
