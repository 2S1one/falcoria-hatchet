import uuid

import pytest

from asm_contracts.chain import ChainStatus, HttpxThenNucleiTask
from asm_contracts.httpx import (
    HttpResult,
    HttpxScanResult,
    HttpxScanTask,
    HttpxTarget,
    ScanAttempt,
    ScanStatus,
    Scheme,
)
from asm_contracts.nuclei import NucleiScanParams
from asm_contracts.nuclei_task import NucleiScanTask
from asm_core.chain import run_chain

pytestmark = pytest.mark.anyio

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _task(hostname: str | None) -> HttpxThenNucleiTask:
    return HttpxThenNucleiTask(
        project_id=_PROJECT,
        scan_id=_SCAN,
        target=HttpxTarget(target_id=0, ip="192.0.2.1", port=8080, hostname=hostname),
    )


def _answer(task: HttpxScanTask, *, http: bool) -> HttpxScanResult:
    if http:
        attempt = ScanAttempt(
            scheme=Scheme.HTTP,
            status=ScanStatus.SUCCEEDED,
            result=HttpResult(status_code=200, url="http://x/", headers={}, body_size=1),
        )
    else:
        attempt = ScanAttempt(scheme=Scheme.HTTPS, status=ScanStatus.UNREACHABLE, error="refused")
    return HttpxScanResult(target=task.target, attempts=[attempt])


class _Recorder:
    def __init__(self, *, http: bool) -> None:
        self._http = http
        self.httpx_tasks: list[HttpxScanTask] = []
        self.saved: list[tuple[HttpxThenNucleiTask, HttpxScanResult]] = []
        self.nuclei_tasks: list[NucleiScanTask] = []

    async def scan_httpx(self, task: HttpxScanTask) -> HttpxScanResult:
        self.httpx_tasks.append(task)
        return _answer(task, http=self._http)

    async def save_httpx(self, task: HttpxThenNucleiTask, result: HttpxScanResult) -> None:
        self.saved.append((task, result))

    async def start_nuclei(self, task: NucleiScanTask) -> None:
        self.nuclei_tasks.append(task)


async def test_non_http_target_skips_nuclei() -> None:
    recorder = _Recorder(http=False)

    outcome = await run_chain(
        _task(None),
        recorder.scan_httpx,
        recorder.save_httpx,
        recorder.start_nuclei,
        NucleiScanParams(),
    )

    assert outcome.status == ChainStatus.NOT_HTTP
    assert len(recorder.saved) == 1
    assert recorder.saved[0][1].is_http is False
    assert len(recorder.httpx_tasks) == 1
    assert recorder.nuclei_tasks == []


async def test_http_target_starts_nuclei_on_its_hostname_and_port() -> None:
    recorder = _Recorder(http=True)

    outcome = await run_chain(
        _task("app.example.com"),
        recorder.scan_httpx,
        recorder.save_httpx,
        recorder.start_nuclei,
        NucleiScanParams(),
    )

    assert outcome.status == ChainStatus.NUCLEI_STARTED
    assert len(recorder.saved) == 1
    assert recorder.saved[0][1].is_http is True
    (nuclei_task,) = recorder.nuclei_tasks
    assert (nuclei_task.target.host, nuclei_task.target.port) == ("app.example.com", 8080)
    assert (nuclei_task.project_id, nuclei_task.scan_id) == (_PROJECT, _SCAN)


async def test_nuclei_falls_back_to_the_ip_without_a_hostname() -> None:
    recorder = _Recorder(http=True)

    await run_chain(
        _task(None),
        recorder.scan_httpx,
        recorder.save_httpx,
        recorder.start_nuclei,
        NucleiScanParams(),
    )

    assert recorder.nuclei_tasks[0].target.host == "192.0.2.1"


async def test_nuclei_is_started_with_the_given_params() -> None:
    recorder = _Recorder(http=True)
    params = NucleiScanParams(templates=["/some/templates"], rate_limit=20)

    await run_chain(
        _task(None), recorder.scan_httpx, recorder.save_httpx, recorder.start_nuclei, params
    )

    assert recorder.nuclei_tasks[0].params == params
