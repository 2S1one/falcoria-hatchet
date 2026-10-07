"""Scan task input shared between tasker and worker."""

from pydantic import BaseModel, Field

from falcoria_contracts.enums import ImportMode
from falcoria_contracts.scan_options import OpenPortsOpts, ServiceOpts


class ScanTask(BaseModel):
    """Input of one scan task: one IP and one port shard."""

    project_id: str
    scan_id: str
    ip: str
    hostnames: list[str] = []
    open_ports_opts: OpenPortsOpts
    service_opts: ServiceOpts | None = Field(
        default=None, description="Service-detection options, or None to skip that phase."
    )
    timeout: int = Field(gt=0, description="Per-IP scan timeout in seconds.")
    mode: ImportMode
