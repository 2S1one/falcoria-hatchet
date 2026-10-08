import logging
from collections.abc import Sequence

from hatchet_sdk import Context, Hatchet

from asm_contracts.chain import ChainOutcome, HttpxThenNucleiTask
from asm_contracts.httpx import HttpxScanResult, HttpxScanTask
from asm_contracts.httpx_store import HttpxStoreTask
from asm_contracts.nuclei_task import NucleiScanStatus, NucleiScanTask
from asm_contracts.persist import PersistNucleiInput, PersistNucleiOutput
from asm_contracts.task_names import (
    HTTPX_SCAN_TASK_NAME,
    HTTPX_STORE_TASK_NAME,
    HTTPX_THEN_NUCLEI_TASK_NAME,
    NUCLEI_SCAN_WORKFLOW_NAME,
    PERSIST_NUCLEI_TASK_NAME,
)
from asm_core.chain import run_chain, run_httpx_store
from asm_core.config import get_chain_settings
from asm_core.constants import (
    BULK_START_SIZE,
    CHAIN_EXECUTION_TIMEOUT,
    CHAIN_SCHEDULE_TIMEOUT,
    PERSIST_EXECUTION_TIMEOUT,
    PERSIST_RETRIES,
    PERSIST_SCHEDULE_TIMEOUT,
)
from asm_core.db.database import get_sessionmaker
from asm_core.persistence.httpx import save_httpx_result
from asm_core.persistence.nuclei import reconcile_target_findings

logger = logging.getLogger(__name__)

hatchet = Hatchet()

# Declarations of tasks that run on other workers; only the name and the models are shared.
_httpx_scan = hatchet.stubs.task(
    name=HTTPX_SCAN_TASK_NAME, input_validator=HttpxScanTask, output_validator=HttpxScanResult
)
_nuclei_scan = hatchet.stubs.workflow(
    name=NUCLEI_SCAN_WORKFLOW_NAME, input_validator=NucleiScanTask
)


async def _save_httpx(task: HttpxThenNucleiTask | HttpxStoreTask, result: HttpxScanResult) -> None:
    async with get_sessionmaker()() as session:
        await save_httpx_result(session, task.project_id, task.scan_id, result)
        await session.commit()


async def _start_nuclei(task: NucleiScanTask) -> object:
    return await _nuclei_scan.aio_run(task, wait_for_result=False)


@hatchet.task(
    name=HTTPX_THEN_NUCLEI_TASK_NAME,
    input_validator=HttpxThenNucleiTask,
    execution_timeout=CHAIN_EXECUTION_TIMEOUT,
    schedule_timeout=CHAIN_SCHEDULE_TIMEOUT,
)
async def httpx_then_nuclei(task: HttpxThenNucleiTask, ctx: Context) -> ChainOutcome:
    """Runs httpx against one target, stores the probe, and starts nuclei if it speaks HTTP."""
    return await run_chain(
        task,
        _httpx_scan.aio_run,
        _save_httpx,
        _start_nuclei,
        get_chain_settings().nuclei_params,
    )


@hatchet.task(
    name=HTTPX_STORE_TASK_NAME,
    input_validator=HttpxStoreTask,
    execution_timeout=CHAIN_EXECUTION_TIMEOUT,
    schedule_timeout=CHAIN_SCHEDULE_TIMEOUT,
)
async def httpx_scan_and_store(task: HttpxStoreTask, ctx: Context) -> HttpxScanResult:
    """Runs httpx against one target and stores the probe as the target's current result."""
    return await run_httpx_store(task, _httpx_scan.aio_run, _save_httpx)


@hatchet.task(
    name=PERSIST_NUCLEI_TASK_NAME,
    input_validator=PersistNucleiInput,
    retries=PERSIST_RETRIES,
    execution_timeout=PERSIST_EXECUTION_TIMEOUT,
    schedule_timeout=PERSIST_SCHEDULE_TIMEOUT,
)
async def persist_nuclei_findings(request: PersistNucleiInput, ctx: Context) -> PersistNucleiOutput:
    """Stores one target's nuclei findings; an error answer stores nothing, so old findings stay."""
    if request.result.status != NucleiScanStatus.SUCCESS:
        logger.warning(
            "nuclei answered an error for %s:%s, nothing stored: %s",
            request.task.target.host,
            request.task.target.port,
            request.result.error,
        )
        return PersistNucleiOutput(stored=False, findings=0)
    async with get_sessionmaker()() as session:
        await reconcile_target_findings(
            session,
            request.task.project_id,
            request.task.scan_id,
            request.task.target,
            request.task.params,
            request.result.findings,
        )
        await session.commit()
    return PersistNucleiOutput(stored=True, findings=len(request.result.findings))


async def start_chain(task: HttpxThenNucleiTask) -> None:
    """Starts the chain for one target without waiting for it."""
    await httpx_then_nuclei.aio_run(task, wait_for_result=False)


async def start_nuclei_scans(tasks: Sequence[NucleiScanTask]) -> None:
    """Starts the nuclei workflow for every task without waiting for any of them."""
    for start in range(0, len(tasks), BULK_START_SIZE):
        chunk = tasks[start : start + BULK_START_SIZE]
        await _nuclei_scan.aio_run_many(
            [_nuclei_scan.create_bulk_run_item(input=task) for task in chunk],
            wait_for_result=False,
        )


async def start_httpx_scans(tasks: Sequence[HttpxStoreTask]) -> None:
    """Starts the httpx store task for every target without waiting for any of them."""
    for start in range(0, len(tasks), BULK_START_SIZE):
        chunk = tasks[start : start + BULK_START_SIZE]
        await httpx_scan_and_store.aio_run_many(
            [httpx_scan_and_store.create_bulk_run_item(input=task) for task in chunk],
            wait_for_result=False,
        )
