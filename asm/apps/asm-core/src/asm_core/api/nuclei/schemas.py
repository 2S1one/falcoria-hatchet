"""Request/response models for the nuclei launch and results endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from asm_contracts.nuclei import NucleiScanParams, NucleiSeverity, NucleiTarget


class NucleiScanIn(BaseModel):
    """What POST /projects/{project_id}/scans/nuclei accepts; scan_id is server-generated, not caller-supplied."""

    targets: list[NucleiTarget]
    params: NucleiScanParams
    timeout: float = Field(
        default=600.0,
        gt=0,
        le=86400,
        description="Wall-clock limit in seconds for the whole nuclei process.",
    )


class NucleiFindingOut(BaseModel):
    """One currently-active nuclei finding, as exposed to an API caller."""

    target_host: str = Field(description="IP or hostname that was scanned.")
    target_port: int = Field(description="Port that was scanned.")
    target_path: str | None = Field(
        description="Path the finding was matched on; None means the port itself, not a specific path."
    )
    template_id: str = Field(description="Nuclei template identifier that produced this finding.")
    matcher_name: str | None = Field(
        description="Disambiguates matches within one template's several matchers; None when the "
        "template has only one, unnamed matcher."
    )
    severity: NucleiSeverity = Field(description="Severity level reported by the template.")
    template_name: str = Field(
        description="Human-readable name of the template that produced this finding."
    )
    description: str | None = Field(
        description="The template's own description text, if it provides one."
    )
    tags: list[str] = Field(description="Tags attached to the template that produced this finding.")
    cwe_ids: list[str] = Field(
        description="CWE identifiers the template's classification maps to, if any."
    )
    cvss_score: float | None = Field(
        description="0-10 CVSS score; None when the template carries no CVSS classification."
    )
    cvss_metrics: str | None = Field(
        description="CVSS vector string (e.g. AV:N/AC:L/.../C:H/I:H/A:H); None alongside cvss_score."
    )
    matched_at: str = Field(
        description="The exact request URL/line that matched, as reported by nuclei."
    )
    extracted_results: list[str] = Field(
        description="Values extracted from the matched response, as defined by the template."
    )
    curl_command: str | None = Field(
        description="Ready-to-replay curl for the request that matched, exactly as nuclei sent it — "
        "including any Authorization/Cookie header the caller configured. Not redacted: for a "
        "default-credential or header-based bypass finding, the header itself is the evidence."
    )
    timestamp: datetime = Field(description="When nuclei reported this finding.")
    first_seen_at: datetime = Field(
        description="When this finding was first recorded; never updated after that."
    )
    last_seen_at: datetime = Field(
        description="When this finding was most recently reconfirmed by a scan."
    )


class NucleiLaunchOut(BaseModel):
    """Confirms one nuclei scan was started (covering every target in the request), without waiting for it to finish."""

    scan_id: str
