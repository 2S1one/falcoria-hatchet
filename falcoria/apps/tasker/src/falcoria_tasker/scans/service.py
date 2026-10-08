"""Scan-orchestration pipeline: dedup/resolve/shard targets, then start the runs."""

import asyncio
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_names import META_IP, META_PROJECT_SCAN, scan_id_from_key
from falcoria_tasker.config import get_app_settings
from falcoria_tasker.hatchet import runs
from falcoria_tasker.scanledger import ScanledgerClient, get_scanledger_client
from falcoria_tasker.scans.resolve import resolve_targets
from falcoria_tasker.scans.schemas import (
    NotScannedDetails,
    RunningTarget,
    RunScanRequest,
    RunScanResponse,
    ScanListResponse,
    ScanState,
    ScanStatusResponse,
    ScanSummary,
    SkippedCounts,
)
from falcoria_tasker.scans.sharding import shard_ports
from falcoria_tasker.scans.targets import partition_targets, remove_duplicates


@dataclass(slots=True)
class PreparedTargets:
    """Deduped/resolved targets, ready for INSERT-mode dedup and task building."""

    deduped: list[str]
    public_ip_hostnames: dict[str, list[str]]
    private_ip_sources: dict[str, list[str]]
    unresolvable_hosts: list[str]


@dataclass(slots=True)
class InsertModeDedup:
    """Which candidate IPs scanledger already knows, or are running elsewhere."""

    already_known: set[str] = field(default_factory=set)
    already_running: set[str] = field(default_factory=set)

    @property
    def known_only(self) -> set[str]:
        """Known IPs that aren't also currently running (mergeable now)."""
        return self.already_known - self.already_running

    @property
    def skipped_ips(self) -> set[str]:
        """Every IP this scan will not start."""
        return self.already_known | self.already_running


def _merge_sources(*maps: dict[str, list[str]]) -> dict[str, list[str]]:
    """Unions IP -> source-list maps, deduping sources per IP, preserving order."""
    merged: dict[str, list[str]] = {}
    for m in maps:
        for ip, sources in m.items():
            bucket = merged.setdefault(ip, [])
            for source in sources:
                if source not in bucket:
                    bucket.append(source)
    return merged


def _shard_count(request: RunScanRequest) -> int:
    """Returns the port-shard count for request; always 1 in INSERT mode."""
    if request.mode is ImportMode.INSERT or request.sharding is None:
        return 1
    return request.sharding.shard_count


async def _prepare_targets(request: RunScanRequest, semaphore_limit: int) -> PreparedTargets:
    """Dedupes request's hosts, classifies them, and resolves any pending hostnames."""
    deduped = remove_duplicates(request.hosts)
    partition = partition_targets(deduped)
    resolved = await resolve_targets(
        partition.pending_hostnames, request.single_resolve, semaphore_limit
    )
    return PreparedTargets(
        deduped=deduped,
        public_ip_hostnames=_merge_sources(
            {ip: [] for ip in partition.public_ips}, resolved.public_ips
        ),
        private_ip_sources=_merge_sources(partition.private_ips, resolved.private_ips),
        unresolvable_hosts=resolved.unresolvable,
    )


async def _dedupe_insert_mode(
    project_id: UUID, candidates: list[str], scanledger: ScanledgerClient
) -> InsertModeDedup:
    """Read-only: which candidates scanledger already knows, or are queued or running."""
    if not candidates:
        return InsertModeDedup()
    wanted = set(candidates)
    already_known, active = await asyncio.gather(
        scanledger.search_ips(project_id, candidates), runs.active_runs(project_id)
    )
    already_running = {
        ip
        for run in active
        if run.additional_metadata and (ip := run.additional_metadata.get(META_IP)) in wanted
    }
    return InsertModeDedup(already_known, already_running)


async def _merge_known_hostnames(
    project_id: UUID,
    ips: set[str],
    public_ip_hostnames: dict[str, list[str]],
    scanledger: ScanledgerClient,
) -> None:
    """Pushes newly discovered hostnames for skipped-but-known IPs to scanledger.

    Only for IPs scanledger already has on record and that aren't running
    elsewhere right now; the already-running case is deliberately not covered here.
    """
    now = int(time.time())
    items = [
        {"ip": ip, "hostnames": public_ip_hostnames[ip], "endtime": now}
        for ip in sorted(ips)
        if public_ip_hostnames[ip]
    ]
    await scanledger.create_ips(project_id, items, ImportMode.INSERT)


def _build_tasks(
    to_scan: dict[str, list[str]], request: RunScanRequest, project_id: UUID, scan_id: str
) -> list[ScanTask]:
    """Builds one ScanTask per (IP, port-shard), shuffled for load spread."""
    service_opts = request.service_opts if request.include_services else None
    shards = shard_ports(request.open_ports_opts.ports, _shard_count(request))
    tasks = [
        ScanTask(
            project_id=str(project_id),
            scan_id=scan_id,
            ip=ip,
            hostnames=hostnames,
            open_ports_opts=request.open_ports_opts.model_copy(update={"ports": shard}),
            service_opts=service_opts,
            timeout=request.timeout,
            mode=request.mode,
        )
        for ip, hostnames in to_scan.items()
        for shard in shards
    ]
    random.shuffle(tasks)
    return tasks


def _build_summary(
    request: RunScanRequest, prepared: PreparedTargets, dedup: InsertModeDedup, started: int
) -> ScanSummary:
    """Assembles the accounting summary from provided hosts down to started targets."""
    attached_hostnames = len(
        {hostname for hostnames in prepared.public_ip_hostnames.values() for hostname in hostnames}
    )
    return ScanSummary(
        provided=len(request.hosts),
        duplicates_removed=len(request.hosts) - len(prepared.deduped),
        target_ips=len(prepared.public_ip_hostnames),
        attached_hostnames=attached_hostnames,
        skipped=SkippedCounts(
            private_ip=len(prepared.private_ip_sources),
            unresolvable=len(prepared.unresolvable_hosts),
            already_known=len(dedup.known_only),
            already_running=len(dedup.already_running),
        ),
        started=started,
    )


def _build_not_scanned(prepared: PreparedTargets) -> NotScannedDetails:
    """Reports the private and unresolvable targets excluded from the scan."""
    return NotScannedDetails(
        private_targets=prepared.private_ip_sources, unresolvable_hosts=prepared.unresolvable_hosts
    )


async def run_scan(project_id: UUID, request: RunScanRequest) -> RunScanResponse:
    """Dedupes/resolves/shards request's hosts and starts one scan campaign.

    INSERT mode additionally skips IPs scanledger already knows or that are
    currently queued or running under another scan in the project, and pushes any
    newly discovered hostname for a skipped-but-known IP to scanledger directly -
    its own scan is never (re-)run, so nothing else would record it.
    """
    settings = get_app_settings()
    scanledger = get_scanledger_client()

    prepared = await _prepare_targets(request, settings.dns_resolve_semaphore_limit)

    dedup = InsertModeDedup()
    if request.mode is ImportMode.INSERT:
        candidates = list(prepared.public_ip_hostnames)
        dedup = await _dedupe_insert_mode(project_id, candidates, scanledger)
        if dedup.known_only:
            await _merge_known_hostnames(
                project_id, dedup.known_only, prepared.public_ip_hostnames, scanledger
            )

    to_scan = {
        ip: hostnames
        for ip, hostnames in prepared.public_ip_hostnames.items()
        if ip not in dedup.skipped_ips
    }

    scan_id: str | None = None
    if to_scan:
        scan_id = str(uuid4())
        await runs.start_scan_tasks(_build_tasks(to_scan, request, project_id, scan_id))

    summary = _build_summary(request, prepared, dedup, started=len(to_scan))
    return RunScanResponse(
        scan_id=scan_id, summary=summary, not_scanned=_build_not_scanned(prepared)
    )


async def list_running_scans(project_id: UUID) -> ScanListResponse:
    """Lists the project's currently running scans."""
    scan_ids = {
        scan_id_from_key(key)
        for run in await runs.active_runs(project_id)
        if run.additional_metadata and (key := run.additional_metadata.get(META_PROJECT_SCAN))
    }
    return ScanListResponse(running=len(scan_ids), scan_ids=sorted(scan_ids))


def _scan_state(counts: Counter[V1TaskStatus]) -> ScanState:
    """Derives the overall state: running, else cancelled, else failed, else completed."""
    if counts[V1TaskStatus.QUEUED] or counts[V1TaskStatus.RUNNING]:
        return ScanState.RUNNING
    if counts[V1TaskStatus.CANCELLED]:
        return ScanState.CANCELLED
    if counts[V1TaskStatus.FAILED]:
        return ScanState.FAILED
    return ScanState.COMPLETED


async def get_scan_status(project_id: UUID, scan_id: str) -> ScanStatusResponse | None:
    """Returns scan_id's run counts, overall state, and running targets.

    Returns None if no run was ever started for scan_id.
    """
    counts, targets = await asyncio.gather(
        runs.count_by_status(project_id, scan_id), runs.running_targets(project_id, scan_id)
    )
    if not counts:
        return None
    return ScanStatusResponse(
        total=sum(counts.values()),
        queued=counts[V1TaskStatus.QUEUED],
        running=counts[V1TaskStatus.RUNNING],
        completed=counts[V1TaskStatus.COMPLETED],
        failed=counts[V1TaskStatus.FAILED],
        cancelled=counts[V1TaskStatus.CANCELLED],
        state=_scan_state(counts),
        running_targets=[RunningTarget(ip=ip, worker=worker) for ip, worker in targets],
    )


async def cancel_scan(project_id: UUID, scan_id: str) -> None:
    """Cancels one scan's queued and running runs."""
    await runs.cancel_scan(project_id, scan_id)


async def cancel_all_scans(project_id: UUID) -> None:
    """Cancels every queued and running scan run of the project."""
    await runs.cancel_project(project_id)


async def cancel_by_ips(project_id: UUID, ips: list[str]) -> None:
    """Cancels the project's queued and running runs whose IP is in ips."""
    await runs.cancel_ips(project_id, set(ips))
