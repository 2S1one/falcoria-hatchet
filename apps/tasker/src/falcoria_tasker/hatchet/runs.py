"""Hatchet run operations for scans: start, list, count by status, and cancel.

Scan identity lives in run metadata (see falcoria_contracts.scan_names). A metadata
filter with several keys matches ANY of them, so every call below filters on one key.
Each IP is one workflow run of two tasks, so listings and counts use workflow-level
rows (only_tasks=False); only the scanner's tasks are looked at per worker.
"""

import asyncio
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from hatchet_sdk import BulkCancelReplayOpts
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from hatchet_sdk.clients.rest.models.v1_task_summary import V1TaskSummary

from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_names import (
    META_IP,
    META_PROJECT,
    META_PROJECT_SCAN,
    SCAN_MAX_AGE,
    SCAN_WORKFLOW_NAME,
    project_scan_key,
    scan_run_metadata,
)
from falcoria_tasker.hatchet.client import get_hatchet_client
from falcoria_tasker.hatchet.workers import active_scanners

_ACTIVE = [V1TaskStatus.QUEUED, V1TaskStatus.RUNNING]
_PAGE_SIZE = 500  # runs per list request


def _since() -> datetime:
    """Returns the start of the lookback window (Hatchet's own default is 24 h)."""
    return datetime.now(UTC) - SCAN_MAX_AGE


def _scan_filter(project_id: UUID, scan_id: str) -> dict[str, str]:
    return {META_PROJECT_SCAN: project_scan_key(str(project_id), scan_id)}


async def start_scan_tasks(tasks: list[ScanTask]) -> None:
    """Starts one scan task run per task in one bulk call; returns without waiting."""
    stub = get_hatchet_client().stubs.workflow(name=SCAN_WORKFLOW_NAME, input_validator=ScanTask)
    items = [
        stub.create_bulk_run_item(
            input=task,
            additional_metadata=scan_run_metadata(task.project_id, task.scan_id, task.ip),
        )
        for task in tasks
    ]
    await stub.aio_run_many_no_wait(items)


async def _list_runs(
    metadata: dict[str, str], statuses: list[V1TaskStatus] | None = None
) -> list[V1TaskSummary]:
    """Lists every run matching one metadata pair, across all pages."""
    runs: list[V1TaskSummary] = []
    since = _since()
    while True:
        page = await get_hatchet_client().runs.aio_list(
            since=since,
            additional_metadata=metadata,
            statuses=statuses,
            only_tasks=False,
            include_payloads=False,
            limit=_PAGE_SIZE,
            offset=len(runs),
        )
        rows = page.rows or []
        runs.extend(rows)
        if len(rows) < _PAGE_SIZE:
            return runs


async def count_by_status(project_id: UUID, scan_id: str) -> Counter[V1TaskStatus]:
    """Counts a scan's runs by status; empty if no run was ever started for it.

    One request per status with limit=1: the response carries no total, but its
    page count equals the run count.
    """
    metadata = _scan_filter(project_id, scan_id)
    since = _since()

    async def _count(status: V1TaskStatus) -> int:
        page = await get_hatchet_client().runs.aio_list(
            since=since,
            additional_metadata=metadata,
            statuses=[status],
            only_tasks=False,
            include_payloads=False,
            limit=1,
        )
        return page.pagination.num_pages or 0

    statuses = list(V1TaskStatus)
    counts = await asyncio.gather(*(_count(status) for status in statuses))
    return Counter({status: count for status, count in zip(statuses, counts, strict=True) if count})


async def active_runs(project_id: UUID) -> list[V1TaskSummary]:
    """Lists the project's queued and running scan runs."""
    return await _list_runs({META_PROJECT: str(project_id)}, _ACTIVE)


async def running_targets(project_id: UUID, scan_id: str) -> list[tuple[str, str]]:
    """Lists (ip, worker_name) for one scan's running runs, over active scanner workers only."""
    client = get_hatchet_client()
    metadata = _scan_filter(project_id, scan_id)
    since = _since()
    targets: list[tuple[str, str]] = []
    for worker in await active_scanners():
        page = await client.runs.aio_list(
            since=since,
            additional_metadata=metadata,
            statuses=[V1TaskStatus.RUNNING],
            worker_id=worker.metadata.id,
            only_tasks=True,
            include_payloads=False,
        )
        targets.extend(
            (run.additional_metadata[META_IP], worker.name)
            for run in page.rows or []
            if run.additional_metadata and META_IP in run.additional_metadata
        )
    return targets


async def _cancel_by_metadata(metadata: dict[str, str]) -> None:
    await get_hatchet_client().runs.aio_bulk_cancel_by_filters_with_pagination(
        since=_since(), statuses=_ACTIVE, additional_metadata=metadata
    )


async def cancel_scan(project_id: UUID, scan_id: str) -> None:
    """Cancels a scan's queued and running runs with one bulk call."""
    await _cancel_by_metadata(_scan_filter(project_id, scan_id))


async def cancel_project(project_id: UUID) -> None:
    """Cancels every queued and running scan run of the project."""
    await _cancel_by_metadata({META_PROJECT: str(project_id)})


async def cancel_ips(project_id: UUID, ips: set[str]) -> None:
    """Cancels the project's queued and running runs whose IP is in ips.

    Metadata filters cannot combine project and IP, so the project's active runs
    are listed and matched on the IP here.
    """
    run_ids = [
        run.metadata.id
        for run in await active_runs(project_id)
        if run.additional_metadata and run.additional_metadata.get(META_IP) in ips
    ]
    if run_ids:
        await get_hatchet_client().runs.aio_bulk_cancel(BulkCancelReplayOpts(ids=run_ids))
