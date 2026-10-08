from hatchet_sdk import Context, Hatchet
from hatchet_sdk.runnables.types import BatchMemberId

from asm_contracts.nuclei_task import NucleiScanResult, NucleiScanTask
from asm_contracts.persist import PersistNucleiInput, PersistNucleiOutput
from asm_contracts.task_names import NUCLEI_SCAN_WORKFLOW_NAME, PERSIST_NUCLEI_TASK_NAME
from asm_execution.command import OsCommandRunner
from asm_nuclei_worker.batch import run_batch
from asm_nuclei_worker.config import settings
from asm_nuclei_worker.constants import (
    NUCLEI_BATCH_GROUP_KEY,
    NUCLEI_BATCH_INTERVAL,
    NUCLEI_BATCH_SIZE,
    NUCLEI_EXECUTION_TIMEOUT,
    NUCLEI_PERSIST_RETRIES,
    NUCLEI_SCHEDULE_TIMEOUT,
)

hatchet = Hatchet()
_RUNNER = OsCommandRunner()

# Declaration of the task that stores findings; it runs on the asm-core worker, which owns the database.
_persist = hatchet.stubs.task(
    name=PERSIST_NUCLEI_TASK_NAME,
    input_validator=PersistNucleiInput,
    output_validator=PersistNucleiOutput,
)

nuclei_scan = hatchet.workflow(name=NUCLEI_SCAN_WORKFLOW_NAME, input_validator=NucleiScanTask)


@nuclei_scan.batch_task(
    batch_max_size=NUCLEI_BATCH_SIZE,
    batch_max_interval=NUCLEI_BATCH_INTERVAL,
    batch_group_key=NUCLEI_BATCH_GROUP_KEY,
    execution_timeout=NUCLEI_EXECUTION_TIMEOUT,
    schedule_timeout=NUCLEI_SCHEDULE_TIMEOUT,
)
async def scan(
    tasks: dict[BatchMemberId, NucleiScanTask], ctx: Context
) -> dict[BatchMemberId, NucleiScanResult]:
    """Scans one batch of targets in a single nuclei process."""
    return await run_batch(_RUNNER, settings.nuclei_path, tasks)


@nuclei_scan.task(
    parents=[scan], retries=NUCLEI_PERSIST_RETRIES, schedule_timeout=NUCLEI_SCHEDULE_TIMEOUT
)
async def persist(task: NucleiScanTask, ctx: Context) -> NucleiScanResult:
    """Forwards this target's answer to the task that stores it, and returns the answer."""
    result = ctx.task_output(scan)
    await _persist.aio_run(PersistNucleiInput(task=task, result=result))
    return result
