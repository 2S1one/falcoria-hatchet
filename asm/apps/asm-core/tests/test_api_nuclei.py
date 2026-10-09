import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.nuclei import NucleiFinding, NucleiScanParams, NucleiSeverity, NucleiTarget
from asm_contracts.nuclei_task import NucleiScanTask
from asm_core.api.nuclei import router as router_module
from asm_core.api.nuclei.router import get_nuclei_starter, router
from asm_core.api.nuclei.schemas import NucleiFindingOut
from asm_core.api.nuclei.service import list_findings
from asm_core.api.security import require_project_access
from asm_core.db.database import get_session
from asm_core.persistence.nuclei import reconcile_target_findings

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")


class _Starter:
    def __init__(self) -> None:
        self.started: list[NucleiScanTask] = []

    async def __call__(self, tasks: Sequence[NucleiScanTask]) -> None:
        self.started.extend(tasks)


@pytest.fixture
def starter() -> _Starter:
    return _Starter()


@pytest.fixture
def client(starter: _Starter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[require_project_access] = lambda: None
    app.dependency_overrides[get_nuclei_starter] = lambda: starter
    return TestClient(app)


def _body(hosts: tuple[str, ...] = ("10.0.0.1",), **extra: object) -> dict[str, object]:
    return {"targets": [{"host": host, "port": 443} for host in hosts], "params": {}, **extra}


def test_launch_starts_one_run_per_target_under_one_scan_id(
    client: TestClient, starter: _Starter
) -> None:
    response = client.post(
        f"/projects/{_PROJECT}/scans/nuclei", json=_body(("10.0.0.1", "10.0.0.2"), timeout=120)
    )

    assert response.status_code == 202
    scan_id = uuid.UUID(response.json()["scan_id"])
    assert [task.target.host for task in starter.started] == ["10.0.0.1", "10.0.0.2"]
    assert {task.scan_id for task in starter.started} == {scan_id}
    assert {task.project_id for task in starter.started} == {_PROJECT}
    assert {task.timeout for task in starter.started} == {120.0}


def test_two_launches_get_different_scan_ids(client: TestClient) -> None:
    first = client.post(f"/projects/{_PROJECT}/scans/nuclei", json=_body()).json()["scan_id"]
    second = client.post(f"/projects/{_PROJECT}/scans/nuclei", json=_body()).json()["scan_id"]

    assert first != second


def test_a_caller_supplied_scan_id_is_ignored(client: TestClient, starter: _Starter) -> None:
    client.post(f"/projects/{_PROJECT}/scans/nuclei", json=_body(scan_id=str(_SCAN)))

    assert starter.started[0].scan_id != _SCAN


def test_a_malformed_host_is_rejected_before_anything_starts(
    client: TestClient, starter: _Starter
) -> None:
    response = client.post(
        f"/projects/{_PROJECT}/scans/nuclei",
        json={"targets": [{"host": "bad host\nx", "port": 80}], "params": {}},
    )

    assert response.status_code == 422
    assert starter.started == []


def test_results_endpoint_returns_what_the_service_lists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    finding = NucleiFindingOut(
        target_host="10.0.0.1",
        target_port=443,
        target_path=None,
        template_id="t1",
        matcher_name=None,
        severity=NucleiSeverity.INFO,
        template_name="T1",
        description=None,
        tags=[],
        cwe_ids=[],
        cvss_score=None,
        cvss_metrics=None,
        matched_at="http://10.0.0.1",
        extracted_results=[],
        curl_command=None,
        timestamp=now,
        first_seen_at=now,
        last_seen_at=now,
    )

    async def _fake_list(session: object, project_id: uuid.UUID) -> list[NucleiFindingOut]:
        assert project_id == _PROJECT
        return [finding]

    monkeypatch.setattr(router_module, "list_findings", _fake_list)

    response = client.get(f"/projects/{_PROJECT}/results/nuclei")

    assert response.status_code == 200
    assert [item["template_id"] for item in response.json()] == ["t1"]


@pytest.mark.anyio
@pytest.mark.postgres
async def test_list_findings_returns_only_the_requested_project(session: AsyncSession) -> None:
    target = NucleiTarget(host="app.example.com", port=8080)
    finding = NucleiFinding(
        target=target,
        template_id="a",
        severity=NucleiSeverity.INFO,
        template_name="A",
        matched_at="http://x/",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    other_project = uuid.UUID("00000000-0000-0000-0000-000000000009")
    for project in (_PROJECT, other_project):
        await reconcile_target_findings(
            session, project, _SCAN, target, NucleiScanParams(), [finding]
        )
    await session.commit()

    findings = await list_findings(session, _PROJECT)

    assert [item.template_id for item in findings] == ["a"]
