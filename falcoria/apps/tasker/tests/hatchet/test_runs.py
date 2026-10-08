from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from hatchet_sdk.clients.rest.models.v1_task_status import V1TaskStatus
from hatchet_sdk.clients.rest.models.worker_status import WorkerStatus

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_names import (
    META_IP,
    META_PROJECT,
    META_PROJECT_SCAN,
    ROLE_SCANNER,
    ROLE_UPLOADER,
    SCAN_WORKFLOW_NAME,
    WORKER_ROLE_LABEL,
)
from falcoria_contracts.scan_options import OpenPortsOpts
from falcoria_tasker.hatchet import runs, workers as hatchet_workers

pytestmark = pytest.mark.anyio

PROJECT = uuid4()


def _run(run_id: str, ip: str) -> Any:
    return SimpleNamespace(metadata=SimpleNamespace(id=run_id), additional_metadata={META_IP: ip})


class _FakeRuns:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.list_calls: list[dict[str, Any]] = []
        self.cancel_filters: list[dict[str, Any]] = []
        self.cancelled_ids: list[str] = []
        self.num_pages = 0

    async def aio_list(self, **kwargs: Any) -> Any:
        self.list_calls.append(kwargs)
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", len(self.rows))
        rows = self.rows[offset : offset + limit]
        return SimpleNamespace(rows=rows, pagination=SimpleNamespace(num_pages=self.num_pages))

    async def aio_bulk_cancel_by_filters_with_pagination(self, **kwargs: Any) -> None:
        self.cancel_filters.append(kwargs)

    async def aio_bulk_cancel(self, opts: Any) -> None:
        self.cancelled_ids.extend(opts.ids)


class _FakeStub:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def create_bulk_run_item(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    async def aio_run_many_no_wait(self, items: list[dict[str, Any]]) -> None:
        self.items = items


class _FakeClient:
    def __init__(self, fake_runs: _FakeRuns, stub: _FakeStub | None = None) -> None:
        self.runs = fake_runs
        self.stub = stub or _FakeStub()
        self.stub_args: dict[str, Any] = {}
        self.stubs = SimpleNamespace(workflow=self._task)
        self.workers = SimpleNamespace(aio_list=self._workers)

    def _task(self, **kwargs: Any) -> _FakeStub:
        self.stub_args = kwargs
        return self.stub

    async def _workers(self) -> Any:
        scanner = SimpleNamespace(
            metadata=SimpleNamespace(id="w1"),
            name="worker-a",
            status=WorkerStatus.ACTIVE,
            labels=[SimpleNamespace(key=WORKER_ROLE_LABEL, value=ROLE_SCANNER)],
        )
        uploader = SimpleNamespace(
            metadata=SimpleNamespace(id="w2"),
            name="worker-up",
            status=WorkerStatus.ACTIVE,
            labels=[SimpleNamespace(key=WORKER_ROLE_LABEL, value=ROLE_UPLOADER)],
        )
        stale = SimpleNamespace(
            metadata=SimpleNamespace(id="w3"),
            name="worker-b",
            status=WorkerStatus.INACTIVE,
            labels=[SimpleNamespace(key=WORKER_ROLE_LABEL, value=ROLE_SCANNER)],
        )
        return SimpleNamespace(rows=[scanner, uploader, stale])


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _install(client: _FakeClient) -> _FakeClient:
        monkeypatch.setattr(runs, "get_hatchet_client", lambda: client)
        monkeypatch.setattr(hatchet_workers, "get_hatchet_client", lambda: client)
        return client

    return _install


def _task(ip: str) -> ScanTask:
    return ScanTask(
        project_id=str(PROJECT),
        scan_id="s1",
        ip=ip,
        open_ports_opts=OpenPortsOpts(ports=["22"]),
        timeout=30,
        mode=ImportMode.INSERT,
    )


async def test_start_scan_tasks_sets_metadata_per_run(install: Any) -> None:
    client = install(_FakeClient(_FakeRuns()))

    await runs.start_scan_tasks([_task("10.0.0.1"), _task("10.0.0.2")])

    assert client.stub_args["name"] == SCAN_WORKFLOW_NAME
    assert [item["additional_metadata"][META_IP] for item in client.stub.items] == [
        "10.0.0.1",
        "10.0.0.2",
    ]
    assert client.stub.items[0]["additional_metadata"][META_PROJECT_SCAN] == f"{PROJECT}:s1"


async def test_active_runs_pages_until_a_short_page(
    install: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runs, "_PAGE_SIZE", 2)
    fake = _FakeRuns([_run(str(i), f"10.0.0.{i}") for i in range(5)])
    install(_FakeClient(fake))

    result = await runs.active_runs(PROJECT)

    assert len(result) == 5
    assert [call["offset"] for call in fake.list_calls] == [0, 2, 4]
    assert fake.list_calls[0]["additional_metadata"] == {META_PROJECT: str(PROJECT)}
    assert fake.list_calls[0]["statuses"] == [V1TaskStatus.QUEUED, V1TaskStatus.RUNNING]


async def test_count_by_status_uses_page_count_and_drops_zeros(install: Any) -> None:
    fake = _FakeRuns([_run("1", "10.0.0.1")])
    fake.num_pages = 3
    install(_FakeClient(fake))

    counts = await runs.count_by_status(PROJECT, "s1")

    assert set(counts) == set(V1TaskStatus)
    assert all(count == 3 for count in counts.values())
    assert {call["limit"] for call in fake.list_calls} == {1}


async def test_count_by_status_is_empty_without_runs(install: Any) -> None:
    install(_FakeClient(_FakeRuns()))

    assert await runs.count_by_status(PROJECT, "s1") == {}


async def test_running_targets_pairs_ip_with_scanner_worker_name(install: Any) -> None:
    fake = _FakeRuns([_run("1", "10.0.0.1")])
    install(_FakeClient(fake))

    targets = await runs.running_targets(PROJECT, "s1")

    assert targets == [("10.0.0.1", "worker-a")]
    assert [call["worker_id"] for call in fake.list_calls] == ["w1"]
    assert fake.list_calls[0]["statuses"] == [V1TaskStatus.RUNNING]


async def test_cancel_scan_filters_on_the_composite_key_only(install: Any) -> None:
    fake = _FakeRuns()
    install(_FakeClient(fake))

    await runs.cancel_scan(PROJECT, "s1")

    assert fake.cancel_filters[0]["additional_metadata"] == {META_PROJECT_SCAN: f"{PROJECT}:s1"}
    assert fake.cancel_filters[0]["statuses"] == [V1TaskStatus.QUEUED, V1TaskStatus.RUNNING]
    assert fake.cancel_filters[0]["since"] is not None


async def test_cancel_ips_cancels_only_matching_runs(install: Any) -> None:
    fake = _FakeRuns([_run("a", "10.0.0.1"), _run("b", "10.0.0.2"), _run("c", "10.0.0.3")])
    install(_FakeClient(fake))

    await runs.cancel_ips(PROJECT, {"10.0.0.1", "10.0.0.3"})

    assert fake.cancelled_ids == ["a", "c"]


async def test_cancel_ips_skips_the_call_when_nothing_matches(install: Any) -> None:
    fake = _FakeRuns([_run("a", "10.0.0.1")])
    install(_FakeClient(fake))

    await runs.cancel_ips(PROJECT, {"10.9.9.9"})

    assert fake.cancelled_ids == []
