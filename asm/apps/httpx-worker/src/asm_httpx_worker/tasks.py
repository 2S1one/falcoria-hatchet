from datetime import timedelta
from typing import Final

from hatchet_sdk import Context, Hatchet

from asm_contracts.httpx import HttpxScanResult, HttpxScanTask
from asm_contracts.task_names import HTTPX_SCAN_TASK_NAME
from asm_httpx_worker.runner import run

# One retry = two attempts in total, same as the old activity's maximum_attempts=2.
HTTPX_SCAN_RETRIES: Final = 1
HTTPX_SCAN_TIMEOUT: Final = timedelta(seconds=120)

hatchet = Hatchet()


@hatchet.task(
    name=HTTPX_SCAN_TASK_NAME,
    input_validator=HttpxScanTask,
    retries=HTTPX_SCAN_RETRIES,
    execution_timeout=HTTPX_SCAN_TIMEOUT,
)
async def httpx_scan(task: HttpxScanTask, ctx: Context) -> HttpxScanResult:
    """Runs the httpx scanner for one target."""
    return await run(task.target, task.params)
