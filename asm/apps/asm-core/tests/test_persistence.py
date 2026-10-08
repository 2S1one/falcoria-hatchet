import uuid
from datetime import UTC, datetime

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.chain import HttpxThenNucleiTask
from asm_contracts.httpx import (
    HttpResult,
    HttpxScanResult,
    HttpxTarget,
    ScanAttempt,
    ScanStatus,
    Scheme,
)
from asm_contracts.nuclei import NucleiFinding, NucleiScanParams, NucleiSeverity, NucleiTarget
from asm_core.db.models import HttpxResultCurrentDB, NucleiFindingCurrentDB
from asm_core.persistence.httpx import save_httpx_result
from asm_core.persistence.nuclei import reconcile_target_findings

pytestmark = [pytest.mark.anyio, pytest.mark.postgres]

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN_1 = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_SCAN_2 = uuid.UUID("00000000-0000-0000-0000-0000000000a2")


def _httpx_task(scan_id: uuid.UUID) -> HttpxThenNucleiTask:
    return HttpxThenNucleiTask(
        project_id=_PROJECT,
        scan_id=scan_id,
        target=HttpxTarget(target_id=0, ip="192.0.2.1", port=8080, hostname="app.example.com"),
    )


def _http_result(task: HttpxThenNucleiTask) -> HttpxScanResult:
    attempt = ScanAttempt(
        scheme=Scheme.HTTP,
        status=ScanStatus.SUCCEEDED,
        result=HttpResult(status_code=200, url="http://app/", headers={"server": "x"}, body_size=3),
    )
    return HttpxScanResult(target=task.target, attempts=[attempt])


def _not_http_result(task: HttpxThenNucleiTask) -> HttpxScanResult:
    attempt = ScanAttempt(scheme=Scheme.HTTPS, status=ScanStatus.UNREACHABLE, error="refused")
    return HttpxScanResult(target=task.target, attempts=[attempt])


async def _httpx_rows(session: AsyncSession) -> list[HttpxResultCurrentDB]:
    return list((await session.exec(select(HttpxResultCurrentDB))).all())


async def _finding_rows(session: AsyncSession) -> list[NucleiFindingCurrentDB]:
    return list((await session.exec(select(NucleiFindingCurrentDB))).all())


async def test_httpx_probe_is_stored_with_its_attempts(session: AsyncSession) -> None:
    task = _httpx_task(_SCAN_1)

    await save_httpx_result(session, task.project_id, task.scan_id, _http_result(task))
    await session.commit()

    (row,) = await _httpx_rows(session)
    assert row.is_http is True
    assert row.target_hostname == "app.example.com"
    assert row.attempts[0]["status"] == "succeeded"
    assert row.first_seen_scan_id == row.last_seen_scan_id == _SCAN_1


async def test_a_repeat_probe_updates_the_row_and_keeps_first_seen(session: AsyncSession) -> None:
    first = _httpx_task(_SCAN_1)
    second = _httpx_task(_SCAN_2)
    await save_httpx_result(session, first.project_id, first.scan_id, _http_result(first))
    await session.commit()

    await save_httpx_result(session, second.project_id, second.scan_id, _not_http_result(second))
    await session.commit()

    (row,) = await _httpx_rows(session)
    assert row.is_http is False
    assert row.attempts[0]["status"] == "unreachable"
    assert row.first_seen_scan_id == _SCAN_1
    assert row.last_seen_scan_id == _SCAN_2


def _finding(target: NucleiTarget, template_id: str) -> NucleiFinding:
    return NucleiFinding(
        target=target,
        template_id=template_id,
        severity=NucleiSeverity.INFO,
        template_name=template_id,
        matched_at="http://x/",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )


_TARGET = NucleiTarget(host="app.example.com", port=8080)


async def test_findings_are_stored_and_a_repeat_reconcile_adds_no_duplicates(
    session: AsyncSession,
) -> None:
    findings = [_finding(_TARGET, "a"), _finding(_TARGET, "b")]

    for _ in range(2):
        await reconcile_target_findings(
            session, _PROJECT, _SCAN_1, _TARGET, NucleiScanParams(), findings
        )
        await session.commit()

    assert sorted(row.template_id for row in await _finding_rows(session)) == ["a", "b"]


async def test_a_finding_no_longer_reported_is_removed_when_the_scan_filter_matches(
    session: AsyncSession,
) -> None:
    params = NucleiScanParams()
    await reconcile_target_findings(
        session,
        _PROJECT,
        _SCAN_1,
        _TARGET,
        params,
        [_finding(_TARGET, "a"), _finding(_TARGET, "b")],
    )
    await session.commit()

    await reconcile_target_findings(
        session, _PROJECT, _SCAN_2, _TARGET, params, [_finding(_TARGET, "a")]
    )
    await session.commit()

    (row,) = await _finding_rows(session)
    assert row.template_id == "a"
    assert row.last_seen_scan_id == _SCAN_2
    assert row.first_seen_scan_id == _SCAN_1


async def test_a_finding_is_kept_when_the_later_scan_used_a_different_filter(
    session: AsyncSession,
) -> None:
    await reconcile_target_findings(
        session, _PROJECT, _SCAN_1, _TARGET, NucleiScanParams(), [_finding(_TARGET, "a")]
    )
    await session.commit()

    await reconcile_target_findings(
        session, _PROJECT, _SCAN_2, _TARGET, NucleiScanParams(tags=["cve"]), []
    )
    await session.commit()

    assert [row.template_id for row in await _finding_rows(session)] == ["a"]
