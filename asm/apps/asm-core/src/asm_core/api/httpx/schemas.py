"""Request/response models for the httpx launch and results endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from asm_contracts.httpx import HttpxScanParams, HttpxTarget, ScanAttempt


class HttpxScanIn(BaseModel):
    """What POST /projects/{project_id}/scans/httpx accepts; scan_id is server-generated, not caller-supplied."""

    targets: list[HttpxTarget]
    params: HttpxScanParams = Field(default_factory=HttpxScanParams)


class HttpxLaunchOut(BaseModel):
    """Confirms one httpx scan was started (covering every target in the request), without waiting for it to finish."""

    scan_id: str


class HttpxResultOut(BaseModel):
    """The latest httpx probe of one target, as exposed to an API caller."""

    target_ip: str = Field(description="IP the probe connected to.")
    target_port: int
    target_hostname: str | None = Field(
        description="Host header and TLS SNI the probe presented; None when it used the IP."
    )
    target_path: str
    is_http: bool = Field(
        description="Whether any attempt got an HTTP response. False does not say whether the port is "
        "closed or open without HTTP; the attempt statuses do."
    )
    attempts: list[ScanAttempt] = Field(description="Each scheme tried, and what happened.")
    first_seen_at: datetime = Field(description="When this target was first probed.")
    last_seen_at: datetime = Field(description="When this target was most recently probed.")
