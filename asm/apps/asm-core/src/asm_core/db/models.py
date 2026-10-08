import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, String, UniqueConstraint, Uuid
from sqlmodel import JSON, Field, SQLModel

from asm_contracts.nuclei import NucleiSeverity


class NucleiFindingCurrentDB(SQLModel, table=True):
    """One template match currently believed true for one target — no history of past scans.

    `target_path`/`matcher_name` stay in the uniqueness key with `NULLS NOT DISTINCT`: a NULL there is a
    real, repeatable value (bare host:port, or a template's one unnamed matcher), not "unknown". `scan_filter`
    is the filtering fields of the params that last confirmed this row — used to tell whether a later scan
    that didn't report this finding actually rechecked it.
    """

    __tablename__ = "nuclei_findings_current"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "target_host",
            "target_port",
            "target_path",
            "template_id",
            "matcher_name",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    project_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False, index=True))

    target_host: str
    target_port: int
    target_path: str | None = None

    template_id: str = Field(index=True)
    matcher_name: str | None = None
    severity: NucleiSeverity = Field(sa_column=Column(String, nullable=False, index=True))
    template_name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cwe_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cvss_score: float | None = Field(default=None, sa_column=Column(Float))
    cvss_metrics: str | None = None

    matched_at: str
    extracted_results: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    curl_command: str | None = None
    timestamp: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    first_seen_scan_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False))
    first_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_seen_scan_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False))
    last_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    scan_filter: dict = Field(sa_column=Column(JSON, nullable=False))


class HttpxResultCurrentDB(SQLModel, table=True):
    """The latest httpx probe of one target — no history of past probes.

    A row with `is_http` false is the recorded outcome of a target that did not answer over HTTP;
    `attempts` holds each scheme's status and error, so the reason is kept. `target_hostname` and
    `target_path` stay in the uniqueness key with `NULLS NOT DISTINCT`, like the nuclei table.
    """

    __tablename__ = "httpx_results_current"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "target_ip",
            "target_port",
            "target_hostname",
            "target_path",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    project_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False, index=True))

    target_ip: str
    target_port: int
    target_hostname: str | None = None
    target_path: str = "/"

    is_http: bool = Field(sa_column=Column(Boolean, nullable=False, index=True))
    attempts: list[dict] = Field(sa_column=Column(JSON, nullable=False))

    first_seen_scan_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False))
    first_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_seen_scan_id: uuid.UUID = Field(sa_column=Column(Uuid, nullable=False))
    last_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
