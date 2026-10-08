"""Reconciliation of one target's nuclei findings against current state."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from asm_contracts.nuclei import NucleiFinding, NucleiScanParams, NucleiTarget
from asm_core.db.models import NucleiFindingCurrentDB

_SCAN_FILTER_FIELDS = {"templates", "tags", "severity", "exclude_severity", "protocol_types"}

_CONFLICT_KEY = [
    "project_id",
    "target_host",
    "target_port",
    "target_path",
    "template_id",
    "matcher_name",
]


async def reconcile_target_findings(
    session: AsyncSession,
    project_id: uuid.UUID,
    scan_id: uuid.UUID,
    target: NucleiTarget,
    params: NucleiScanParams,
    findings: Sequence[NucleiFinding],
) -> None:
    """Make nuclei_findings_current match `findings` for this one target.

    Upserts every reported finding (insert new, refresh an existing one's descriptive fields and
    last_seen_*/scan_filter) via ON CONFLICT DO UPDATE, so concurrent or repeated reconciliation of the
    same target can't create duplicate rows. Deletes a stored finding no longer reported, but only when
    this scan's filter exactly matches the filter that last confirmed it; otherwise leaves it alone, since
    coverage is unknown. The delete isn't conflict-guarded like the upsert is, so a concurrent reconciliation
    of the same target could race it; a resolved row that's missed self-corrects on the next reconciliation.
    Does not commit.
    """
    scan_filter = params.model_dump(mode="json", include=_SCAN_FILTER_FIELDS)
    now = datetime.now(UTC)

    existing = (
        await session.exec(
            select(NucleiFindingCurrentDB).where(
                NucleiFindingCurrentDB.project_id == project_id,
                NucleiFindingCurrentDB.target_host == target.host,
                NucleiFindingCurrentDB.target_port == target.port,
                NucleiFindingCurrentDB.target_path == target.path,
            )
        )
    ).all()

    reported_keys = {(f.template_id, f.matcher_name) for f in findings}
    resolved = [
        row
        for row in existing
        if (row.template_id, row.matcher_name) not in reported_keys
        and row.scan_filter == scan_filter
    ]

    if findings:
        await _upsert_findings(session, project_id, scan_id, target, scan_filter, now, findings)
    for row in resolved:
        await session.delete(row)


async def _upsert_findings(
    session: AsyncSession,
    project_id: uuid.UUID,
    scan_id: uuid.UUID,
    target: NucleiTarget,
    scan_filter: dict,
    now: datetime,
    findings: Sequence[NucleiFinding],
) -> None:
    """Insert new findings, or refresh an existing one's descriptive fields and last_seen_*/scan_filter."""
    rows = [
        {
            "project_id": project_id,
            "target_host": target.host,
            "target_port": target.port,
            "target_path": target.path,
            "first_seen_scan_id": scan_id,
            "first_seen_at": now,
            "last_seen_scan_id": scan_id,
            "last_seen_at": now,
            "scan_filter": scan_filter,
            **finding.model_dump(exclude={"target"}),
        }
        for finding in findings
    ]
    statement = pg_insert(NucleiFindingCurrentDB).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=_CONFLICT_KEY,
        set_={
            "severity": statement.excluded.severity,
            "template_name": statement.excluded.template_name,
            "description": statement.excluded.description,
            "tags": statement.excluded.tags,
            "cwe_ids": statement.excluded.cwe_ids,
            "cvss_score": statement.excluded.cvss_score,
            "cvss_metrics": statement.excluded.cvss_metrics,
            "matched_at": statement.excluded.matched_at,
            "extracted_results": statement.excluded.extracted_results,
            "curl_command": statement.excluded.curl_command,
            "timestamp": statement.excluded.timestamp,
            "last_seen_scan_id": statement.excluded.last_seen_scan_id,
            "last_seen_at": statement.excluded.last_seen_at,
            "scan_filter": statement.excluded.scan_filter,
        },
    )
    connection = await session.connection()
    await connection.execute(statement)
