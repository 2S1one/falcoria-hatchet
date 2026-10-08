"""Impure orchestration of one nuclei batch scan: build the command, run it, parse its JSONL output."""

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from asm_contracts.nuclei import NucleiFinding, NucleiScanParams, NucleiSeverity, NucleiTarget
from asm_execution.command import CommandRunner
from asm_nuclei_worker.args import build_command

logger = logging.getLogger(__name__)


class _NucleiClassification(BaseModel):
    """The `info.classification` block; only the fields we read."""

    model_config = ConfigDict(extra="ignore")
    cwe_ids: list[str] = Field(alias="cwe-id", default_factory=list)
    cvss_score: float | None = Field(alias="cvss-score", default=None)
    cvss_metrics: str | None = Field(alias="cvss-metrics", default=None)

    @field_validator("cwe_ids", mode="before")
    @classmethod
    def _null_to_empty(cls, v: object) -> object:
        """Nuclei may emit `"cwe-id": null` when a template carries no CWE mapping."""
        return v or []


class _NucleiInfo(BaseModel):
    """The `info` block of a nuclei event; only the fields we read."""

    model_config = ConfigDict(extra="ignore")
    name: str
    description: str | None = None
    severity: NucleiSeverity
    tags: list[str] = Field(default_factory=list)
    classification: _NucleiClassification | None = None


class _NucleiEvent(BaseModel):
    """One JSONL line nuclei emits for a match; only the fields we read, the rest ignored."""

    model_config = ConfigDict(extra="ignore")
    template_id: str = Field(alias="template-id")
    matcher_name: str | None = Field(alias="matcher-name", default=None)
    info: _NucleiInfo
    matched_at: str = Field(alias="matched-at")
    host: str
    port: int | str | None = None
    url: str | None = None
    extracted_results: list[str] = Field(alias="extracted-results", default_factory=list)
    curl_command: str | None = Field(alias="curl-command", default=None)
    timestamp: datetime

    @field_validator("extracted_results", mode="before")
    @classmethod
    def _null_to_empty(cls, v: object) -> object:
        """Nuclei may emit `"extracted-results": null`; treat it as no results."""
        return v or []


def nuclei_input(target: NucleiTarget) -> str:
    """One `-l` line, `host:port[/path]`; no scheme — nuclei's own probe picks http/https."""
    return f"{_host_port(target.host, target.port)}{target.path or ''}"


async def scan_batch(
    runner: CommandRunner,
    nuclei_path: str,
    targets: list[NucleiTarget],
    params: NucleiScanParams,
    timeout: float,
) -> list[NucleiFinding]:
    """Runs nuclei against a batch of targets in one subprocess; each finding carries its target."""
    by_line = {nuclei_input(target): target for target in targets}
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", encoding="utf-8", delete_on_close=False
    ) as list_file:
        list_file.write("\n".join(by_line) + "\n")
        list_file.close()  # flush to disk; the file stays until the with-block exits
        command = build_command(nuclei_path, Path(list_file.name), params)
        stdout = await runner.run(command, timeout=timeout)
    return _parse_findings(stdout, by_line)


def _parse_findings(stdout: bytes, by_line: dict[str, NucleiTarget]) -> list[NucleiFinding]:
    """Parses nuclei's JSONL stdout; a malformed line or one matching no target is logged and dropped."""
    findings: list[NucleiFinding] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        finding = _parse_line(line, by_line)
        if finding is not None:
            findings.append(finding)
    return findings


def _parse_line(line: bytes, by_line: dict[str, NucleiTarget]) -> NucleiFinding | None:
    """One JSONL line to a finding, or None if it isn't usable. Never raises; a bad line is logged."""
    try:
        event = _NucleiEvent.model_validate_json(line)
    except ValidationError as exc:
        logger.warning("Dropping unparsable nuclei output line: %s | %r", exc, line[:200])
        return None
    input_line = _input_line(event.url, event.host, event.port)
    target = by_line.get(input_line) if input_line is not None else None
    if target is None:
        logger.warning(
            "Nuclei finding matched no target | template=%s input=%s", event.template_id, input_line
        )
        return None
    return NucleiFinding(
        target=target,
        template_id=event.template_id,
        matcher_name=event.matcher_name,
        severity=event.info.severity,
        template_name=event.info.name,
        description=event.info.description,
        tags=event.info.tags,
        cwe_ids=event.info.classification.cwe_ids if event.info.classification else [],
        cvss_score=event.info.classification.cvss_score if event.info.classification else None,
        cvss_metrics=event.info.classification.cvss_metrics if event.info.classification else None,
        matched_at=event.matched_at,
        extracted_results=event.extracted_results,
        curl_command=event.curl_command,
        timestamp=event.timestamp,
    )


def _input_line(url: str | None, host: str, port: int | str | None) -> str | None:
    """The `-l` line an event came from: `url` without its scheme, or `host:port` when there's no `url` (ssl).

    None when the event has neither (dns: domain-level, no port), so it can't belong to any target.
    """
    if url is not None:
        return url.removeprefix("https://").removeprefix("http://")
    if port is None:
        return None
    return _host_port(host, port)


def _host_port(host: str, port: int | str) -> str:
    """`host:port`, with an IPv6 host in brackets."""
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
