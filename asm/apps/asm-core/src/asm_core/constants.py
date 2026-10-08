from datetime import timedelta
from typing import Final

# The chain task waits only for httpx (seconds), then starts nuclei without waiting.
CHAIN_EXECUTION_TIMEOUT: Final = timedelta(minutes=10)
# A target waits here for a free slot of the chain worker.
CHAIN_SCHEDULE_TIMEOUT: Final = timedelta(days=1)
CHAIN_WORKER_SLOTS: Final = 500

# Storing is idempotent, so a failed attempt can simply be tried again.
PERSIST_RETRIES: Final = 2
PERSIST_EXECUTION_TIMEOUT: Final = timedelta(minutes=2)
PERSIST_SCHEDULE_TIMEOUT: Final = timedelta(days=1)

SCANLEDGER_POLL_INTERVAL_SEC: Final = 5

# Runs sent to the engine in one bulk call.
BULK_START_SIZE: Final = 250
