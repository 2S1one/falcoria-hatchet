from typing import Any

import pytest

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_io import ScanTask
from falcoria_contracts.scan_options import OpenPortsOpts, ServiceOpts
from falcoria_worker import scan
from falcoria_worker.config import AppSettings
from falcoria_worker.scan import ScanReport, scan_ip, upload_report

pytestmark = pytest.mark.anyio


def _task(**overrides: Any) -> ScanTask:
    fields: dict[str, Any] = {
        "project_id": "p1",
        "scan_id": "s1",
        "ip": "10.0.0.1",
        "hostnames": ["a.example.com"],
        "open_ports_opts": OpenPortsOpts(ports=["22", "80"]),
        "timeout": 30,
        "mode": ImportMode.INSERT,
    }
    return ScanTask.model_validate(fields | overrides)


def _patch_run_nmap_scan(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    async def fake_run_nmap_scan(*args: Any) -> str:
        calls.append(args)
        return "<nmaprun/>"

    monkeypatch.setattr(scan, "run_nmap_scan", fake_run_nmap_scan)
    return calls


async def test_scan_ip_builds_args_from_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_run_nmap_scan(monkeypatch)
    settings = AppSettings(nmap_path="/usr/bin/nmap")

    report = await scan_ip(_task(), settings)

    assert report == ScanReport(xml="<nmaprun/>")
    _executor, nmap_path, target, open_ports_args, service_args, timeout, hostnames = calls[0]
    assert (nmap_path, target, timeout, hostnames) == (
        "/usr/bin/nmap",
        "10.0.0.1",
        30,
        ["a.example.com"],
    )
    assert "-p 22,80" in open_ports_args
    assert service_args is None


async def test_scan_ip_adds_service_args_when_service_opts_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_run_nmap_scan(monkeypatch)

    await scan_ip(_task(service_opts=ServiceOpts(os_detection=True)), AppSettings())

    service_args = calls[0][4]
    assert "-sV" in service_args
    assert "-O" in service_args


async def test_upload_report_sends_the_task_identity_and_xml() -> None:
    sent: list[tuple[str, str, ImportMode, str]] = []

    class _Scanledger:
        async def upload_report(
            self, project_id: str, scan_id: str, mode: ImportMode, xml: str
        ) -> dict[str, Any]:
            sent.append((project_id, scan_id, mode, xml))
            return {}

    await upload_report(_task(), ScanReport(xml="<x/>"), _Scanledger())

    assert sent == [("p1", "s1", ImportMode.INSERT, "<x/>")]
