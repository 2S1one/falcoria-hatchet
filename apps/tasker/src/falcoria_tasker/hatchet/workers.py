"""Hatchet worker lookups: the active scanner workers."""

from hatchet_sdk.clients.rest.models.worker import Worker
from hatchet_sdk.clients.rest.models.worker_status import WorkerStatus

from falcoria_contracts.scan_names import ROLE_SCANNER, WORKER_ROLE_LABEL
from falcoria_tasker.hatchet.client import get_hatchet_client


def _is_scanner(worker: Worker) -> bool:
    return any(
        label.key == WORKER_ROLE_LABEL and label.value == ROLE_SCANNER
        for label in worker.labels or []
    )


async def active_scanners() -> list[Worker]:
    """Lists the active workers that run scans (not the report uploaders)."""
    listed = await get_hatchet_client().workers.aio_list()
    return [
        worker
        for worker in listed.rows or []
        if worker.status == WorkerStatus.ACTIVE and _is_scanner(worker)
    ]
