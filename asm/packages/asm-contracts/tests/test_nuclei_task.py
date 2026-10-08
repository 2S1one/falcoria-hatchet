import uuid

import pytest

from asm_contracts.nuclei import NucleiScanParams, NucleiTarget
from asm_contracts.nuclei_task import NucleiScanResult, NucleiScanStatus, NucleiScanTask

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_SCAN = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _task(**overrides: object) -> NucleiScanTask:
    fields: dict[str, object] = {
        "project_id": _PROJECT,
        "scan_id": _SCAN,
        "target": NucleiTarget(host="192.0.2.1", port=80),
        "params": NucleiScanParams(),
    }
    return NucleiScanTask.model_validate({**fields, **overrides})


def test_batch_key_is_shared_by_tasks_that_differ_only_in_target() -> None:
    first = _task(target=NucleiTarget(host="192.0.2.1", port=80))
    second = _task(target=NucleiTarget(host="192.0.2.2", port=8080))

    assert first.batch_key == second.batch_key


@pytest.mark.parametrize(
    "overrides",
    [
        {"scan_id": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        {"project_id": uuid.UUID("00000000-0000-0000-0000-000000000003")},
        {"params": NucleiScanParams(rate_limit=10)},
        {"timeout": 60.0},
    ],
)
def test_batch_key_differs_when_scan_params_or_timeout_differ(
    overrides: dict[str, object],
) -> None:
    assert _task(**overrides).batch_key != _task().batch_key


def test_batch_key_is_part_of_the_serialized_task_and_survives_a_round_trip() -> None:
    task = _task()

    dumped = task.model_dump(mode="json")

    assert dumped["batch_key"] == task.batch_key
    assert NucleiScanTask.model_validate(dumped) == task


def test_error_result_carries_the_error_text_and_no_findings() -> None:
    result = NucleiScanResult(
        target=NucleiTarget(host="192.0.2.1", port=80),
        status=NucleiScanStatus.ERROR,
        error="nuclei timed out",
    )

    assert result.findings == []
    assert NucleiScanResult.model_validate(result.model_dump(mode="json")) == result
