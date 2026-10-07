"""The scan workflow: a scanner task, then an upload task, routed to workers by role."""

from datetime import timedelta
from functools import lru_cache

from hatchet_sdk import Context, DesiredWorkerLabel, Hatchet
from hatchet_sdk.runnables.workflow import Workflow

from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_names import (
    ROLE_SCANNER,
    ROLE_UPLOADER,
    SCAN_MAX_AGE,
    SCAN_WORKFLOW_NAME,
    WORKER_ROLE_LABEL,
)
from falcoria_worker.config import get_app_settings, get_scanledger_settings
from falcoria_worker.constants import SCAN_TASK_NAME, UPLOAD_TASK_NAME
from falcoria_worker.scan import ScanReport, scan_ip, upload_report
from falcoria_worker.scanledger import ScanledgerClient

# Hatchet takes execution_timeout when the task is declared, not per run. The per-pass
# timeout from the request is enforced by the executor; this is only the outer bound
# (two passes of at most 24 h each, plus a margin).
_SCAN_EXECUTION_TIMEOUT = timedelta(days=2, hours=1)
_UPLOAD_EXECUTION_TIMEOUT = timedelta(minutes=5)


@lru_cache
def _get_scanledger() -> ScanledgerClient:
    """Returns the uploader's scanledger client, built on first use."""
    settings = get_scanledger_settings()
    return ScanledgerClient(
        settings.base_url, settings.token.get_secret_value(), verify=settings.tls_verify
    )


async def close_scanledger() -> None:
    """Closes the scanledger client if one was built."""
    if _get_scanledger.cache_info().currsize:
        await _get_scanledger().aclose()


def build_workflow(hatchet: Hatchet) -> Workflow[ScanTask]:
    """Declares the scan workflow on `hatchet`."""
    workflow = hatchet.workflow(name=SCAN_WORKFLOW_NAME, input_validator=ScanTask)

    @workflow.task(
        name=SCAN_TASK_NAME,
        retries=1,
        execution_timeout=_SCAN_EXECUTION_TIMEOUT,
        schedule_timeout=SCAN_MAX_AGE,
        desired_worker_labels={
            WORKER_ROLE_LABEL: DesiredWorkerLabel(value=ROLE_SCANNER, required=True)
        },
    )
    async def scan(input: ScanTask, ctx: Context) -> ScanReport:
        return await scan_ip(input, get_app_settings())

    @workflow.task(
        name=UPLOAD_TASK_NAME,
        parents=[scan],
        retries=3,
        backoff_factor=2.0,
        backoff_max_seconds=10,
        execution_timeout=_UPLOAD_EXECUTION_TIMEOUT,
        schedule_timeout=SCAN_MAX_AGE,
        desired_worker_labels={
            WORKER_ROLE_LABEL: DesiredWorkerLabel(value=ROLE_UPLOADER, required=True)
        },
    )
    async def upload(input: ScanTask, ctx: Context) -> None:
        await upload_report(input, ctx.task_output(scan), _get_scanledger())

    return workflow
