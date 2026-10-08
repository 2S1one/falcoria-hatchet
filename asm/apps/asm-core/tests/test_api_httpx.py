import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_contracts.httpx import (
    HttpResult,
    HttpxScanParams,
    HttpxScanResult,
    HttpxScanTask,
    HttpxTarget,
    ScanAttempt,
    ScanStatus,
    Scheme,
)
from asm_contracts.httpx_store import HttpxStoreTask
from asm_core.api.httpx import router as router_module
from asm_core.api.httpx.router import get_httpx_starter, router
from asm_core.api.httpx.schemas import HttpxResultOut
from asm_core.api.httpx.service import list_results
from asm_core.chain import run_httpx_store
from asm_core.db.database import get_session
from asm_core.persistence.httpx import save_httpx_result

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")


class _Starter:
    def __init__(self) -> None:
        self.started: list[HttpxStoreTask] = []

    async def __call__(self, tasks: Sequence[HttpxStoreTask]) -> None:
        self.started.extend(tasks)


@pytest.fixture
def starter() -> _Starter:
    return _Starter()


@pytest.fixture
def client(starter: _Starter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[get_httpx_starter] = lambda: starter
    return TestClient(app)


def _target(ip: str, port: int = 80) -> dict[str, object]:
    return {"target_id": 1, "ip": ip, "port": port}


def test_launch_starts_one_run_per_target_under_one_scan_id(
    client: TestClient, starter: _Starter
) -> None:
    response = client.post(
        f"/projects/{_PROJECT}/scans/httpx",
        json={
            "targets": [_target("10.0.0.1"), _target("10.0.0.2", 8080)],
            "params": {"http_timeout": 3},
        },
    )

    assert response.status_code == 202
    scan_id = uuid.UUID(response.json()["scan_id"])
    assert [(task.target.ip, task.target.port) for task in starter.started] == [
        ("10.0.0.1", 80),
        ("10.0.0.2", 8080),
    ]
    assert {task.scan_id for task in starter.started} == {scan_id}
    assert {task.project_id for task in starter.started} == {_PROJECT}
    assert {task.params.http_timeout for task in starter.started} == {3.0}


def test_params_default_when_the_request_has_none(client: TestClient, starter: _Starter) -> None:
    client.post(f"/projects/{_PROJECT}/scans/httpx", json={"targets": [_target("10.0.0.1")]})

    assert starter.started[0].params == HttpxScanParams()


def test_a_target_without_an_ip_is_rejected_before_anything_starts(
    client: TestClient, starter: _Starter
) -> None:
    response = client.post(
        f"/projects/{_PROJECT}/scans/httpx", json={"targets": [{"target_id": 1, "port": 80}]}
    )

    assert response.status_code == 422
    assert starter.started == []


def test_results_endpoint_returns_what_the_service_lists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    item = HttpxResultOut(
        target_ip="10.0.0.1",
        target_port=80,
        target_hostname=None,
        target_path="/",
        is_http=False,
        attempts=[ScanAttempt(scheme=Scheme.HTTPS, status=ScanStatus.UNREACHABLE, error="refused")],
        first_seen_at=now,
        last_seen_at=now,
    )

    async def _fake_list(session: object, project_id: uuid.UUID) -> list[HttpxResultOut]:
        assert project_id == _PROJECT
        return [item]

    monkeypatch.setattr(router_module, "list_results", _fake_list)

    response = client.get(f"/projects/{_PROJECT}/results/httpx")

    assert response.status_code == 200
    (body,) = response.json()
    assert body["is_http"] is False
    assert body["attempts"][0]["status"] == "unreachable"


@pytest.mark.anyio
async def test_run_httpx_store_probes_with_the_requested_params_and_stores_the_probe() -> None:
    task = HttpxStoreTask(
        project_id=_PROJECT,
        scan_id=_SCAN,
        target=HttpxTarget(target_id=0, ip="192.0.2.1", port=80),
        params=HttpxScanParams(http_timeout=2.0),
    )
    probes: list[HttpxScanParams] = []
    saved: list[tuple[HttpxStoreTask, HttpxScanResult]] = []
    answer = ScanAttempt(
        scheme=Scheme.HTTP,
        status=ScanStatus.SUCCEEDED,
        result=HttpResult(status_code=200, url="http://x/", headers={}, body_size=1),
    )

    async def scan(probe_task: HttpxScanTask) -> HttpxScanResult:
        probes.append(probe_task.params)
        return HttpxScanResult(target=task.target, attempts=[answer])

    async def save(stored_task: HttpxStoreTask, result: HttpxScanResult) -> None:
        saved.append((stored_task, result))

    result = await run_httpx_store(task, scan, save)

    assert probes == [HttpxScanParams(http_timeout=2.0)]
    assert saved == [(task, result)]
    assert result.is_http is True


@pytest.mark.anyio
@pytest.mark.postgres
async def test_list_results_returns_only_the_requested_project(session: AsyncSession) -> None:
    other_project = uuid.UUID("00000000-0000-0000-0000-000000000009")
    chain_task = HttpxThenNucleiTask(
        project_id=_PROJECT,
        scan_id=_SCAN,
        target=HttpxTarget(target_id=0, ip="192.0.2.1", port=8080),
    )
    attempt = ScanAttempt(scheme=Scheme.HTTPS, status=ScanStatus.UNREACHABLE, error="refused")
    result = HttpxScanResult(target=chain_task.target, attempts=[attempt])
    for project in (_PROJECT, other_project):
        await save_httpx_result(session, project, _SCAN, result)
    await session.commit()

    results = await list_results(session, _PROJECT)

    assert [(item.target_ip, item.target_port, item.is_http) for item in results] == [
        ("192.0.2.1", 8080, False)
    ]
    assert results[0].attempts[0].status == ScanStatus.UNREACHABLE
