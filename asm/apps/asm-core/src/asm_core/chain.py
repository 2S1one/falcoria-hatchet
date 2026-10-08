import logging
from collections.abc import Awaitable, Callable

from asm_contracts.chain import ChainOutcome, ChainStatus, HttpxThenNucleiTask
from asm_contracts.httpx import HttpxScanParams, HttpxScanResult, HttpxScanTask
from asm_contracts.httpx_store import HttpxStoreTask
from asm_contracts.nuclei import NucleiScanParams, NucleiTarget
from asm_contracts.nuclei_task import NucleiScanTask

logger = logging.getLogger(__name__)


async def run_chain(
    task: HttpxThenNucleiTask,
    scan_httpx: Callable[[HttpxScanTask], Awaitable[HttpxScanResult]],
    save_httpx: Callable[[HttpxThenNucleiTask, HttpxScanResult], Awaitable[None]],
    start_nuclei: Callable[[NucleiScanTask], Awaitable[object]],
    nuclei_params: NucleiScanParams,
) -> ChainOutcome:
    """Probes the target with httpx, stores the probe, and starts nuclei without waiting if it speaks HTTP.

    The httpx scan params are the defaults; nuclei scans `hostname` when known, else `ip`, on the same port,
    with `nuclei_params`.
    The probe is stored for every target, so a target that is not HTTP still has a recorded outcome.
    """
    result = await scan_httpx(HttpxScanTask(target=task.target, params=HttpxScanParams()))
    await save_httpx(task, result)
    if not result.is_http:
        logger.info("not http, nuclei skipped: %s:%s", task.target.ip, task.target.port)
        return ChainOutcome(target=task.target, status=ChainStatus.NOT_HTTP)
    await start_nuclei(
        NucleiScanTask(
            project_id=task.project_id,
            scan_id=task.scan_id,
            target=NucleiTarget(host=task.target.hostname or task.target.ip, port=task.target.port),
            params=nuclei_params,
        )
    )
    return ChainOutcome(target=task.target, status=ChainStatus.NUCLEI_STARTED)


async def run_httpx_store(
    task: HttpxStoreTask,
    scan_httpx: Callable[[HttpxScanTask], Awaitable[HttpxScanResult]],
    save_httpx: Callable[[HttpxStoreTask, HttpxScanResult], Awaitable[None]],
) -> HttpxScanResult:
    """Probes the target with httpx and stores the probe as its current result."""
    result = await scan_httpx(HttpxScanTask(target=task.target, params=task.params))
    await save_httpx(task, result)
    return result
