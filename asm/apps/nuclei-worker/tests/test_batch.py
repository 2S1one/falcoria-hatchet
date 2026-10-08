import json
import uuid

import pytest

from asm_contracts.nuclei import NucleiScanParams, NucleiTarget
from asm_contracts.nuclei_task import NucleiScanStatus, NucleiScanTask
from asm_execution.command import CommandExecutionError, CommandTimeoutError
from asm_nuclei_worker.batch import NUCLEI_MAX_ATTEMPTS, run_batch

pytestmark = pytest.mark.anyio

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")
_FIRST = NucleiTarget(host="192.0.2.1", port=80)
_SECOND = NucleiTarget(host="192.0.2.2", port=8080)


def _event(host: str, port: int) -> dict[str, object]:
    return {
        "template-id": "probe-200",
        "info": {"name": "Probe 200", "severity": "info"},
        "type": "http",
        "host": host,
        "port": str(port),
        "url": f"http://{host}:{port}",
        "matched-at": f"http://{host}:{port}/",
        "timestamp": "2024-01-01T00:00:00Z",
    }


def _tasks() -> dict[str, NucleiScanTask]:
    return {
        key: NucleiScanTask(
            project_id=_PROJECT, scan_id=_SCAN, target=target, params=NucleiScanParams()
        )
        for key, target in (("a", _FIRST), ("b", _SECOND))
    }


class _ScriptedRunner:
    """Replays one outcome per call: bytes are returned, exceptions are raised."""

    def __init__(self, *outcomes: bytes | Exception) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def run(self, command: list[str], *, timeout: float | None = None) -> bytes:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


async def test_each_member_gets_only_its_own_findings() -> None:
    stdout = "\n".join(json.dumps(_event("192.0.2.1", 80)) for _ in range(2)).encode("utf-8")
    runner = _ScriptedRunner(stdout)

    answers = await run_batch(runner, "nuclei", _tasks())

    assert answers["a"].status == NucleiScanStatus.SUCCESS
    assert len(answers["a"].findings) == 2
    assert answers["b"].status == NucleiScanStatus.SUCCESS
    assert answers["b"].findings == []
    assert runner.calls == 1


async def test_a_failed_run_is_retried_once_and_then_succeeds() -> None:
    runner = _ScriptedRunner(CommandExecutionError("exit 1"), b"")

    answers = await run_batch(runner, "nuclei", _tasks())

    assert {answer.status for answer in answers.values()} == {NucleiScanStatus.SUCCESS}
    assert runner.calls == 2


async def test_a_run_that_keeps_failing_answers_error_after_the_last_attempt() -> None:
    runner = _ScriptedRunner(*[CommandExecutionError("exit 1")] * NUCLEI_MAX_ATTEMPTS)

    answers = await run_batch(runner, "nuclei", _tasks())

    assert runner.calls == NUCLEI_MAX_ATTEMPTS
    assert set(answers) == {"a", "b"}
    for answer in answers.values():
        assert answer.status == NucleiScanStatus.ERROR
        assert answer.error == "exit 1"
        assert answer.findings == []


async def test_a_timeout_is_not_retried() -> None:
    runner = _ScriptedRunner(CommandTimeoutError("timed out"), b"")

    answers = await run_batch(runner, "nuclei", _tasks())

    assert runner.calls == 1
    assert {answer.status for answer in answers.values()} == {NucleiScanStatus.ERROR}
    assert {answer.error for answer in answers.values()} == {"timed out"}


async def test_an_unexpected_error_still_answers_every_member() -> None:
    runner = _ScriptedRunner(FileNotFoundError("nuclei"))

    answers = await run_batch(runner, "nuclei", _tasks())

    assert runner.calls == 1
    assert {answer.status for answer in answers.values()} == {NucleiScanStatus.ERROR}
