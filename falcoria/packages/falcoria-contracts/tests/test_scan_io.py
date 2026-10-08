import pytest
from pydantic import ValidationError

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_options import OpenPortsOpts, ServiceOpts


def _task(**overrides: object) -> ScanTask:
    fields: dict[str, object] = {
        "project_id": "proj-1",
        "scan_id": "scan-1",
        "ip": "10.0.0.1",
        "open_ports_opts": OpenPortsOpts(ports=["22", "80"]),
        "timeout": 30,
        "mode": ImportMode.INSERT,
    }
    return ScanTask.model_validate(fields | overrides)


def test_scan_task_defaults() -> None:
    task = _task()

    assert task.service_opts is None
    assert task.hostnames == []


def test_scan_task_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValidationError):
        _task(timeout=0)


def test_scan_task_round_trips_through_json() -> None:
    task = _task(
        service_opts=ServiceOpts(os_detection=True),
        hostnames=["host.example.com"],
        mode=ImportMode.REPLACE,
    )

    assert ScanTask.model_validate(task.model_dump(mode="json")) == task
