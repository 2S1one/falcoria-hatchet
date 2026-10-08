import ipaddress
import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

_HOSTNAME_RE = re.compile(
    r"\A(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z"
)


def _validate_host(v: str) -> str:
    """Accept an IP (v4/v6) or a DNS hostname; reject anything else, e.g. a newline that would add a scan line."""
    try:
        ipaddress.ip_address(v)
    except ValueError:
        if not _HOSTNAME_RE.match(v):
            raise ValueError(f"host is neither an IP address nor a valid hostname: {v!r}") from None
    return v


class NucleiSeverity(StrEnum):
    """Template severity levels nuclei accepts in -s and reports on findings."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class NucleiProtocolType(StrEnum):
    """Template protocol types nuclei accepts in -pt.

    `file` and `code` are left out: those templates stay disabled.
    """

    # DNS = "dns"  # not supported yet: domain-level, events carry no port/url
    HTTP = "http"
    # HEADLESS = "headless"  # not supported yet: needs -headless and a browser on the worker
    TCP = "tcp"
    WORKFLOW = "workflow"
    SSL = "ssl"
    WEBSOCKET = "websocket"
    WHOIS = "whois"
    JAVASCRIPT = "javascript"


class NucleiTarget(BaseModel):
    """What nuclei scans: `host:port[/path]`. No id, so equal targets mean the same scan."""

    host: str = Field(description="IP or hostname; nuclei resolves a hostname itself.")
    port: int = Field(ge=1, le=65535)
    path: str | None = Field(
        default=None,
        pattern=r"\A/\S+\z",
        description=(
            "None = the port itself, all template types. A path (never bare '/') runs HTTP "
            "templates on it; nuclei skips ssl templates for any path."
        ),
    )

    @field_validator("host")
    @classmethod
    def _check_host(cls, v: str) -> str:
        return _validate_host(v)


class NucleiScanParams(BaseModel):
    """Tuning knobs for one nuclei scan; part of the batching key, so any difference splits batches.

    Numeric defaults mirror nuclei's own. None means the flag is not passed at all.
    """

    templates: list[str] | None = Field(
        default=None,
        description=(
            "-t: template files or directories to run; None = nuclei's default template set"
        ),
    )
    severity: list[NucleiSeverity] | None = Field(
        default=None,
        description="-s: run only templates of these severities; None = no severity filter",
    )
    exclude_severity: list[NucleiSeverity] | None = Field(
        default=None,
        description="-es: skip templates of these severities; None = nothing excluded",
    )
    protocol_types: list[NucleiProtocolType] | None = Field(
        default=None,
        description="-pt: run only templates of these protocol types; None = all types",
    )
    tags: list[str] | None = Field(
        default=None, description="-tags: run only templates with these tags; None = no tag filter"
    )

    rate_limit: int = Field(
        default=150,
        ge=1,
        le=10000,
        description="-rl: max requests per second for the whole nuclei process",
    )
    rate_limit_duration: str = Field(
        default="1s",
        pattern=r"^\d+(ms|s|m)$",
        description="-rld: time window -rl applies to",
    )
    bulk_size: int = Field(
        default=25, ge=1, le=1000, description="-bs: max hosts scanned in parallel per template"
    )
    concurrency: int = Field(
        default=25, ge=1, le=1000, description="-c: max templates executed in parallel"
    )
    js_concurrency: int = Field(
        default=120, ge=1, le=1000, description="-jsc: max JavaScript runtimes in parallel"
    )
    payload_concurrency: int = Field(
        default=25, ge=1, le=1000, description="-pc: max payload concurrency per template"
    )
    probe_concurrency: int = Field(
        default=50, ge=1, le=1000, description="-prc: HTTP probe concurrency"
    )
    template_loading_concurrency: int = Field(
        default=50, ge=1, le=1000, description="-tlc: max concurrent template loads"
    )
    timeout: int = Field(
        default=10, ge=1, le=300, description="-timeout: seconds to wait for each request"
    )
    retries: int = Field(
        default=1, ge=0, le=10, description="-retries: times to retry a failed request"
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description=(
            "-H: extra request headers, name to value; each is sent as its own -H 'Name: value'. "
            "Examples: Host for IP pinning, Authorization for auth, Scan: Falcoria for scan "
            "identification. None = no extra headers"
        ),
    )
    sni: str | None = Field(
        default=None,
        description="-sni: TLS SNI hostname; None = nuclei's default (the input's domain name)",
    )
    no_interactsh: bool = Field(
        default=True,
        description=(
            "-ni: disable interactsh and skip OAST templates; True = no OAST callbacks leave the "
            "worker. Set False to send OAST callbacks to ProjectDiscovery's public interactsh server."
        ),
    )
    disable_update_check: bool = Field(
        default=True, description="-duc: skip nuclei's startup check for nuclei/template updates"
    )

    @field_validator("templates", "tags")
    @classmethod
    def _no_comma_join_hazard(cls, v: list[str] | None) -> list[str] | None:
        """Reject a blank or comma-containing item: these are comma-joined into one nuclei flag, so a comma splits one value into several."""
        for item in v or []:
            if not item.strip() or "," in item:
                raise ValueError(
                    f"invalid list item {item!r}: must be non-blank and contain no comma"
                )
        return v


class NucleiFinding(BaseModel):
    """One template match from a nuclei scan."""

    target: NucleiTarget
    template_id: str
    matcher_name: str | None = Field(
        default=None,
        description=(
            "Disambiguates matches within one template's several matchers (e.g. which security "
            "header is missing); None when the template has only one, unnamed matcher."
        ),
    )
    severity: NucleiSeverity
    template_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    cwe_ids: list[str] = Field(default_factory=list)
    cvss_score: float | None = Field(
        default=None,
        description="0-10 CVSS score; None when the template carries no CVSS classification.",
    )
    cvss_metrics: str | None = Field(
        default=None,
        description="CVSS vector string (e.g. AV:N/AC:L/.../C:H/I:H/A:H); None alongside cvss_score.",
    )
    matched_at: str
    extracted_results: list[str] = Field(default_factory=list)
    curl_command: str | None = Field(
        default=None,
        description=(
            "Ready-to-replay curl for the request that matched, exactly as nuclei sent it — "
            "including any Authorization/Cookie header the caller configured via "
            "NucleiScanParams.headers. Not redacted: for a default-credential or header-based "
            "bypass finding, the header itself is the evidence."
        ),
    )
    timestamp: datetime


class NucleiBatchScanInput(BaseModel):
    """Everything run_nuclei_batch_scan needs for one batch run."""

    targets: list[NucleiTarget]
    params: NucleiScanParams
    timeout: float
