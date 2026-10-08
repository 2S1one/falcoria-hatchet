"""Scan option models shared by tasker (request validation) and worker (argument building)."""

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from falcoria_contracts.enums import PortProtocol


class CommonScanOpts(BaseModel):
    """Timing and retry knobs shared by the open-ports and service-detection phases."""

    dns_resolution: bool | None = Field(default=None, description="-n (False), -R (True)")
    max_retries: int | None = Field(default=None, ge=0, le=20, description="--max-retries")
    min_rtt_timeout_ms: int | None = Field(
        default=None, ge=1, le=60000, description="--min-rtt-timeout"
    )
    max_rtt_timeout_ms: int | None = Field(
        default=None, ge=1, le=60000, description="--max-rtt-timeout"
    )
    initial_rtt_timeout_ms: int | None = Field(
        default=None, ge=1, le=60000, description="--initial-rtt-timeout"
    )
    min_rate: int | None = Field(default=None, ge=1, le=30000, description="--min-rate")
    max_rate: int | None = Field(default=None, ge=1, le=30000, description="--max-rate")


class ScanType(str, Enum):
    """TCP scan technique for the open-ports phase."""

    SYN = "syn"
    CONNECT = "connect"


class OpenPortsOpts(CommonScanOpts):
    """Options for the open-ports discovery phase, which always runs."""

    transport_protocol: PortProtocol = PortProtocol.TCP
    scan_type: ScanType = Field(
        default=ScanType.SYN, description="-sS (syn, default) / -sT (connect)"
    )
    ports: list[str] = Field(min_length=1, description="Ports or ranges, e.g. '22', '1000-2000'.")
    skip_host_discovery: bool = Field(default=True, description="-Pn")

    @field_validator("ports")
    @classmethod
    def _validate_ports(cls, ports: list[str]) -> list[str]:
        for port in ports:
            if "-" in port:
                parts = port.split("-")
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    raise ValueError(f"Invalid port range format: {port}")
                start, end = map(int, parts)
                if not (1 <= start <= end <= 65535):
                    raise ValueError(f"Port range out of bounds: {port}")
            elif not port.isdigit() or not (1 <= int(port) <= 65535):
                raise ValueError(f"Invalid port: {port}")
        return ports


class ServiceOpts(CommonScanOpts):
    """Options for the optional service-detection phase."""

    aggressive_scan: bool = Field(default=False, description="-A")
    default_scripts: bool = Field(default=False, description="-sC")
    os_detection: bool = Field(default=False, description="-O")
    traceroute: bool = Field(default=False, description="--traceroute")
    version_intensity: int | None = Field(
        default=None, ge=0, le=9, description="--version-intensity"
    )
