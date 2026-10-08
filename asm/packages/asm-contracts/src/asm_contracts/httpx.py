from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from asm_contracts.common import ScannerName


class Scheme(StrEnum):
    """HTTP scheme actually attempted for one probe — never guessed, only observed."""

    HTTP = "http"
    HTTPS = "https"


class ScanStatus(StrEnum):
    """Outcome of one scheme attempt, distinguishing why it didn't succeed when it didn't."""

    SUCCEEDED = "succeeded"
    TLS_REJECTED = "tls_rejected"
    TLS_HANDSHAKE_FAILED = "tls_handshake_failed"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    REQUEST_FAILED = "request_failed"


class HttpxTarget(BaseModel):
    """Identity of one httpx scan target. Worker connects to `ip` regardless of `hostname`."""

    target_id: int = Field(description="Caller-assigned; never generated here.")
    ip: str
    port: int
    hostname: str | None = Field(
        default=None,
        description=(
            "Presented as the Host header and TLS SNI when set; falls back to `ip` when unset — "
            "either way, the actual TCP connection target is unaffected (see transport.pinned_client)."
        ),
    )
    path: str = "/"


class HttpxScanParams(BaseModel):
    """Tuning knobs for one httpx scan, always supplied by the caller — no worker-side defaults."""

    http_timeout: float = 10.0


class ScanTaskBase(BaseModel):
    """Shared shape every scanner's task follows.

    No `scanner` field — the task's own concrete type, and the task name it is dispatched under,
    already say which scanner it's for.
    """

    target: HttpxTarget


class HttpxScanTask(ScanTaskBase):
    """One httpx scan task."""

    params: HttpxScanParams


class HttpResult(BaseModel):
    """Successful outcome of one scheme attempt. Only populated when the attempt's status succeeded.

    Not resolved past redirects — a 3xx response (with its Location header, in `headers`) is the result
    as-is.
    """

    status_code: int
    url: str
    headers: dict
    body_size: int = Field(
        description="Bytes actually received (`len(response.content)`), not a reported "
        "`Content-Length` header."
    )


class ScanAttempt(BaseModel):
    """One scheme (http or https) actually tried against a target, and what happened."""

    scheme: Scheme
    status: ScanStatus
    result: HttpResult | None = Field(
        default=None, description="Set only when `status` is `SUCCEEDED`; `None` otherwise."
    )
    error: str | None = Field(
        default=None, description="Set only when `status` isn't `SUCCEEDED`; `None` otherwise."
    )


class ScanResultBase(BaseModel):
    """Shared shape every scanner's result follows."""

    target: HttpxTarget


class HttpxScanResult(ScanResultBase):
    """Full result of one httpx scan — up to two attempts (https first, http only on TLS failure)."""

    scanner: Literal[ScannerName.HTTPX] = ScannerName.HTTPX
    attempts: list[ScanAttempt]

    @computed_field
    @property
    def is_http(self) -> bool:
        """Whether any attempt, over http or https, got an HTTP response.

        False does not say whether the port is closed or open without HTTP; the attempt statuses do.
        """
        return any(attempt.status == ScanStatus.SUCCEEDED for attempt in self.attempts)
