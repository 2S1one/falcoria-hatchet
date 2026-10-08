"""Tests for scans/service.py."""

import json
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import aiodns
import httpx
import pytest
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from pydantic import SecretStr

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_names import META_IP, META_PROJECT_SCAN
from falcoria_contracts.scan_options import OpenPortsOpts, ServiceOpts
from falcoria_tasker.config import AppSettings
from falcoria_tasker.hatchet import runs as runs_module
from falcoria_tasker.scanledger import ScanledgerClient
from falcoria_tasker.scans.schemas import (
    RunningTarget,
    RunScanRequest,
    ScanListResponse,
    ScanState,
    ScanStatusResponse,
    ShardingConfig,
)
from falcoria_tasker.scans.service import (
    InsertModeDedup,
    PreparedTargets,
    _build_not_scanned,
    _build_summary,
    _build_tasks,
    _merge_sources,
    _scan_state,
    _shard_count,
    cancel_all_scans,
    cancel_by_ips,
    cancel_scan,
    get_scan_status,
    list_running_scans,
    run_scan,
)

pytestmark = pytest.mark.anyio

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")


def _request(
    hosts: list[str],
    mode: ImportMode = ImportMode.INSERT,
    include_services: bool = False,
    sharding: ShardingConfig | None = None,
) -> RunScanRequest:
    return RunScanRequest(
        hosts=hosts,
        open_ports_opts=OpenPortsOpts(ports=["22", "80"]),
        service_opts=ServiceOpts(),
        timeout=30,
        include_services=include_services,
        mode=mode,
        sharding=sharding,
    )


# --- _merge_sources ---


def test_merge_sources_unions_and_dedupes() -> None:
    merged = _merge_sources({"1.1.1.1": ["a"]}, {"1.1.1.1": ["a", "b"], "2.2.2.2": ["c"]})

    assert merged == {"1.1.1.1": ["a", "b"], "2.2.2.2": ["c"]}


# --- _shard_count ---


def test_shard_count_forces_one_in_insert_mode() -> None:
    request = _request(["1.1.1.1"], mode=ImportMode.INSERT, sharding=ShardingConfig(shard_count=5))

    assert _shard_count(request) == 1


def test_shard_count_defaults_to_one_without_sharding_config() -> None:
    request = _request(["1.1.1.1"], mode=ImportMode.REPLACE)

    assert _shard_count(request) == 1


def test_shard_count_uses_config_outside_insert_mode() -> None:
    request = _request(["1.1.1.1"], mode=ImportMode.REPLACE, sharding=ShardingConfig(shard_count=4))

    assert _shard_count(request) == 4


# --- _build_tasks ---


def test_build_tasks_builds_one_task_per_ip_without_sharding() -> None:
    request = _request(["1.1.1.1", "2.2.2.2"])
    to_scan = {"1.1.1.1": ["a.example.com"], "2.2.2.2": []}

    tasks = _build_tasks(to_scan, request, PROJECT_ID, "scan-1")

    assert {t.ip for t in tasks} == {"1.1.1.1", "2.2.2.2"}
    assert all(t.service_opts is None for t in tasks)
    assert all(t.project_id == str(PROJECT_ID) and t.scan_id == "scan-1" for t in tasks)
    by_ip = {t.ip: t for t in tasks}
    assert by_ip["1.1.1.1"].hostnames == ["a.example.com"]


def test_build_tasks_includes_service_opts_when_requested() -> None:
    request = _request(["1.1.1.1"], include_services=True)

    tasks = _build_tasks({"1.1.1.1": []}, request, PROJECT_ID, "scan-1")

    assert tasks[0].service_opts == request.service_opts


def test_build_tasks_shards_ports_outside_insert_mode() -> None:
    request = _request(["1.1.1.1"], mode=ImportMode.REPLACE, sharding=ShardingConfig(shard_count=2))

    tasks = _build_tasks({"1.1.1.1": []}, request, PROJECT_ID, "scan-1")

    assert len(tasks) == 2
    assert {tuple(t.open_ports_opts.ports) for t in tasks} == {("22",), ("80",)}


# --- InsertModeDedup ---


def test_insert_mode_dedup_known_only_excludes_running() -> None:
    dedup = InsertModeDedup(already_known={"1.1.1.1", "2.2.2.2"}, already_running={"2.2.2.2"})

    assert dedup.known_only == {"1.1.1.1"}
    assert dedup.skipped_ips == {"1.1.1.1", "2.2.2.2"}


# --- _build_summary / _build_not_scanned ---


def _prepared(**overrides: object) -> PreparedTargets:
    base: dict[str, object] = {
        "deduped": ["1.1.1.1"],
        "public_ip_hostnames": {"1.1.1.1": []},
        "private_ip_sources": {},
        "unresolvable_hosts": [],
    }
    base.update(overrides)
    return PreparedTargets(**base)  # type: ignore[arg-type]


def test_build_summary_basic_accounting() -> None:
    request = _request(["1.1.1.1", "1.1.1.1"])
    prepared = _prepared(deduped=["1.1.1.1"], public_ip_hostnames={"1.1.1.1": []})

    summary = _build_summary(request, prepared, InsertModeDedup(), started=1)

    assert summary.provided == 2
    assert summary.duplicates_removed == 1
    assert summary.target_ips == 1
    assert summary.started == 1
    assert summary.skipped.already_known == 0


def test_build_summary_counts_known_only_not_already_running() -> None:
    request = _request(["1.1.1.1", "2.2.2.2", "3.3.3.3"])
    prepared = _prepared(
        deduped=["1.1.1.1", "2.2.2.2", "3.3.3.3"],
        public_ip_hostnames={"1.1.1.1": [], "2.2.2.2": [], "3.3.3.3": []},
    )
    dedup = InsertModeDedup(already_known={"2.2.2.2", "3.3.3.3"}, already_running={"3.3.3.3"})

    summary = _build_summary(request, prepared, dedup, started=1)

    assert summary.skipped.already_known == 1
    assert summary.skipped.already_running == 1
    assert summary.started == 1


def test_build_summary_counts_unique_attached_hostnames() -> None:
    request = _request(["a.example.com", "b.example.com"])
    prepared = _prepared(
        deduped=["a.example.com", "b.example.com"],
        public_ip_hostnames={"9.9.9.9": ["a.example.com", "b.example.com"]},
    )

    summary = _build_summary(request, prepared, InsertModeDedup(), started=1)

    assert summary.attached_hostnames == 2


def test_build_summary_attached_hostnames_dedupes_a_fanned_out_hostname() -> None:
    request = _request(["cdn.example.com"])
    prepared = _prepared(
        deduped=["cdn.example.com"],
        public_ip_hostnames={"9.9.9.9": ["cdn.example.com"], "9.9.9.10": ["cdn.example.com"]},
    )

    summary = _build_summary(request, prepared, InsertModeDedup(), started=2)

    assert summary.attached_hostnames == 1
    assert summary.target_ips == 2


def test_build_not_scanned_reports_private_and_unresolvable() -> None:
    prepared = _prepared(
        private_ip_sources={"10.0.0.1": ["10.0.0.0/24"]}, unresolvable_hosts=["dead.example.com"]
    )

    not_scanned = _build_not_scanned(prepared)

    assert not_scanned.private_targets == {"10.0.0.1": ["10.0.0.0/24"]}
    assert not_scanned.unresolvable_hosts == ["dead.example.com"]


@dataclass
class _FakeRecord:
    host: str


class _FakeResolver:
    def __init__(self, responses: dict[str, list[list[str]] | Exception]) -> None:
        self._responses = responses

    async def query(self, hostname: str, record_type: str) -> list[_FakeRecord]:
        response = self._responses[hostname]
        if isinstance(response, Exception):
            raise response
        return [_FakeRecord(host=ip) for ip in response[0]]


def _patch_resolver(
    monkeypatch: pytest.MonkeyPatch, responses: dict[str, list[list[str]] | Exception]
) -> None:
    resolver = _FakeResolver(responses)
    monkeypatch.setattr("falcoria_tasker.scans.resolve.get_dns_resolver", lambda: resolver)


def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = AppSettings(
        scanledger_base_url="http://scanledger.test/api",
        scanledger_token=SecretStr("svc-token"),
        dns_resolve_semaphore_limit=10,
    )
    monkeypatch.setattr("falcoria_tasker.scans.service.get_app_settings", lambda: settings)


def _patch_scanledger(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    client = ScanledgerClient(
        "http://scanledger.test/api",
        "svc-token",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )
    monkeypatch.setattr("falcoria_tasker.scans.service.get_scanledger_client", lambda: client)


def _scanledger_handler(known: set[str], create_calls: list[list[dict[str, object]]]):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ips/search"):
            body = json.loads(request.content)
            matched = set(body["filter"]["ip_in"]) & known
            items = [
                {"ip": ip, "first_seen": 0, "last_seen": 0, "hostnames": [], "ports": []}
                for ip in matched
            ]
            return httpx.Response(200, json={"items": items, "total": len(items)})
        assert request.url.path.endswith("/ips")
        create_calls.append(json.loads(request.content))
        return httpx.Response(201, json={"created": [], "updated": [], "unchanged": []})

    return handler


# --- run_scan (integration) ---


def _run(ip: str, key: str | None = None) -> Any:
    metadata = {META_IP: ip}
    if key is not None:
        metadata[META_PROJECT_SCAN] = key
    return SimpleNamespace(additional_metadata=metadata)


def _patch_runs(
    monkeypatch: pytest.MonkeyPatch, active: list[Any] | None = None
) -> list[list[ScanTask]]:
    started: list[list[ScanTask]] = []

    async def fake_active_runs(project_id: UUID) -> list[Any]:
        return active or []

    async def fake_start_scan_tasks(tasks: list[ScanTask]) -> None:
        started.append(tasks)

    monkeypatch.setattr(runs_module, "active_runs", fake_active_runs)
    monkeypatch.setattr(runs_module, "start_scan_tasks", fake_start_scan_tasks)
    return started


async def test_run_scan_insert_mode_merges_hostnames_for_known_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch)
    create_calls: list[list[dict[str, object]]] = []
    _patch_scanledger(monkeypatch, _scanledger_handler({"9.9.9.1", "9.9.9.2"}, create_calls))
    started = _patch_runs(monkeypatch, active=[_run("9.9.9.2")])
    _patch_resolver(
        monkeypatch,
        {"known.example.com": [["9.9.9.1"]], "running.example.com": [["9.9.9.2"]]},
    )

    request = _request(["known.example.com", "running.example.com", "9.9.9.3"])

    response = await run_scan(PROJECT_ID, request)

    assert len(create_calls) == 1
    items = create_calls[0]
    assert len(items) == 1
    assert items[0]["ip"] == "9.9.9.1"
    assert items[0]["hostnames"] == ["known.example.com"]
    assert isinstance(items[0]["endtime"], int)

    assert len(started) == 1
    assert [t.ip for t in started[0]] == ["9.9.9.3"]

    assert response.scan_id is not None
    assert started[0][0].scan_id == response.scan_id
    assert response.summary.started == 1
    assert response.summary.skipped.already_known == 1
    assert response.summary.skipped.already_running == 1


async def test_run_scan_non_insert_mode_skips_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("scanledger should not be called outside INSERT mode")

    _patch_scanledger(monkeypatch, handler)
    started = _patch_runs(monkeypatch)

    request = _request(["1.1.1.1"], mode=ImportMode.REPLACE, sharding=ShardingConfig(shard_count=2))

    response = await run_scan(PROJECT_ID, request)

    assert response.scan_id is not None
    assert len(started[0]) == 2
    assert response.summary.skipped.already_known == 0
    assert response.summary.skipped.already_running == 0


async def test_run_scan_returns_no_scan_id_when_everything_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch)
    _patch_scanledger(monkeypatch, _scanledger_handler({"9.9.9.1"}, []))
    started = _patch_runs(monkeypatch)

    request = _request(["9.9.9.1"])

    response = await run_scan(PROJECT_ID, request)

    assert response.scan_id is None
    assert started == []
    assert response.summary.started == 0


async def test_run_scan_reports_private_and_unresolvable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    _patch_scanledger(monkeypatch, _scanledger_handler(set(), []))
    _patch_runs(monkeypatch)
    _patch_resolver(monkeypatch, {"dead.example.com": aiodns.error.DNSError("nope")})

    request = _request(["10.0.0.5", "dead.example.com"], mode=ImportMode.REPLACE)

    response = await run_scan(PROJECT_ID, request)

    assert response.not_scanned.private_targets == {"10.0.0.5": []}
    assert response.not_scanned.unresolvable_hosts == ["dead.example.com"]
    assert response.summary.skipped.private_ip == 1
    assert response.summary.skipped.unresolvable == 1


# --- list_running_scans / get_scan_status ---


async def test_list_running_scans_dedupes_and_sorts_scan_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runs(
        monkeypatch,
        active=[
            _run("1.1.1.1", f"{PROJECT_ID}:b"),
            _run("1.1.1.2", f"{PROJECT_ID}:a"),
            _run("1.1.1.3", f"{PROJECT_ID}:b"),
        ],
    )

    result = await list_running_scans(PROJECT_ID)

    assert result == ScanListResponse(running=2, scan_ids=["a", "b"])


def _patch_status(
    monkeypatch: pytest.MonkeyPatch,
    counts: Counter[V1TaskStatus],
    targets: list[tuple[str, str]] | None = None,
) -> None:
    async def fake_count_by_status(project_id: UUID, scan_id: str) -> Counter[V1TaskStatus]:
        return counts

    async def fake_running_targets(project_id: UUID, scan_id: str) -> list[tuple[str, str]]:
        return targets or []

    monkeypatch.setattr(runs_module, "count_by_status", fake_count_by_status)
    monkeypatch.setattr(runs_module, "running_targets", fake_running_targets)


async def test_get_scan_status_returns_none_for_an_unknown_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_status(monkeypatch, Counter())

    assert await get_scan_status(PROJECT_ID, "unknown") is None


async def test_get_scan_status_combines_counts_and_running_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = Counter({V1TaskStatus.COMPLETED: 1, V1TaskStatus.RUNNING: 1, V1TaskStatus.QUEUED: 3})
    _patch_status(monkeypatch, counts, [("10.0.0.1", "worker-1")])

    status = await get_scan_status(PROJECT_ID, "scan-1")

    assert status == ScanStatusResponse(
        total=5,
        queued=3,
        running=1,
        completed=1,
        failed=0,
        cancelled=0,
        state=ScanState.RUNNING,
        running_targets=[RunningTarget(ip="10.0.0.1", worker="worker-1")],
    )


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({V1TaskStatus.QUEUED: 1, V1TaskStatus.FAILED: 1}, ScanState.RUNNING),
        ({V1TaskStatus.RUNNING: 1, V1TaskStatus.CANCELLED: 1}, ScanState.RUNNING),
        ({V1TaskStatus.CANCELLED: 1, V1TaskStatus.FAILED: 1}, ScanState.CANCELLED),
        ({V1TaskStatus.FAILED: 1, V1TaskStatus.COMPLETED: 1}, ScanState.FAILED),
        ({V1TaskStatus.COMPLETED: 2}, ScanState.COMPLETED),
    ],
)
def test_scan_state_priority(counts: dict[V1TaskStatus, int], expected: ScanState) -> None:
    assert _scan_state(Counter(counts)) == expected


# --- cancel ---


async def test_cancel_functions_delegate_to_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    async def fake_cancel_scan(project_id: UUID, scan_id: str) -> None:
        calls.append(("scan", project_id, scan_id))

    async def fake_cancel_project(project_id: UUID) -> None:
        calls.append(("project", project_id))

    async def fake_cancel_ips(project_id: UUID, ips: set[str]) -> None:
        calls.append(("ips", project_id, ips))

    monkeypatch.setattr(runs_module, "cancel_scan", fake_cancel_scan)
    monkeypatch.setattr(runs_module, "cancel_project", fake_cancel_project)
    monkeypatch.setattr(runs_module, "cancel_ips", fake_cancel_ips)

    await cancel_scan(PROJECT_ID, "s1")
    await cancel_all_scans(PROJECT_ID)
    await cancel_by_ips(PROJECT_ID, ["1.1.1.1", "1.1.1.1", "2.2.2.2"])

    assert calls == [
        ("scan", PROJECT_ID, "s1"),
        ("project", PROJECT_ID),
        ("ips", PROJECT_ID, {"1.1.1.1", "2.2.2.2"}),
    ]
