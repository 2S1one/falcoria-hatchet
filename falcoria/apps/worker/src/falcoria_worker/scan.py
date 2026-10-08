"""The two steps of one scan: run the scanner for an IP, then upload its report."""

from typing import Any, Protocol

from pydantic import BaseModel

from falcoria_contracts.enums import ImportMode, ScannerFormat
from falcoria_contracts.scan_io import ScanTask
from falcoria_worker.config import AppSettings
from falcoria_worker.nmap.args import build_open_ports_args, build_service_args
from falcoria_worker.nmap.executor import AsyncCommandExecutor
from falcoria_worker.nmap.scanner import run_nmap_scan

_SCANNER = ScannerFormat.NMAP  # the only scanner implemented so far


class ReportUploader(Protocol):
    """The part of ScanledgerClient the upload step depends on."""

    async def upload_report(
        self, project_id: str, scan_id: str, mode: ImportMode, xml: str
    ) -> dict[str, Any]:
        """Uploads a scanner report for `project_id`, tagged with `scan_id`."""
        ...


class ScanReport(BaseModel):
    """The scanner's merged XML report for one IP, passed from the scan step to the upload step."""

    xml: str


async def scan_ip(task: ScanTask, settings: AppSettings) -> ScanReport:
    """Runs the scanner against task.ip and returns its merged XML report."""
    open_ports_args = build_open_ports_args(task.open_ports_opts, _SCANNER)
    service_args = (
        build_service_args(
            task.service_opts,
            _SCANNER,
            task.open_ports_opts.transport_protocol,
            task.open_ports_opts.scan_type,
        )
        if task.service_opts is not None
        else None
    )
    executor = AsyncCommandExecutor(grace_period_seconds=settings.command_grace_period_seconds)
    xml = await run_nmap_scan(
        executor,
        settings.nmap_path,
        task.ip,
        open_ports_args,
        service_args,
        task.timeout,
        task.hostnames,
    )
    return ScanReport(xml=xml)


async def upload_report(task: ScanTask, report: ScanReport, scanledger: ReportUploader) -> None:
    """Uploads one IP's report to scanledger."""
    await scanledger.upload_report(task.project_id, task.scan_id, task.mode, report.xml)
