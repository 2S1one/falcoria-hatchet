"""Scanledger bridge persistence: dedup ledger and per-project poll cursor."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Uuid, func
from sqlmodel import Field, SQLModel


class ScanledgerBridgeSeenTargetDB(SQLModel, table=True):
    """One row per target already launched for one scan campaign.

    The composite primary key doubles as the `ON CONFLICT DO NOTHING` uniqueness constraint that makes
    re-processing a scanledger event page (at-least-once delivery) safe: a repeat insert is a no-op, so
    the caller launches the chain only when the row is newly inserted. `scan_id` is part of the key so a
    target that reappears under a genuinely new scan campaign is not permanently blocked from being
    rescanned.
    """

    __tablename__ = "scanledger_bridge_seen_targets"  # pyright: ignore[reportAssignmentType]

    project_id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    scan_id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    target: str = Field(sa_column=Column(String, primary_key=True))
    port: int = Field(sa_column=Column(Integer, primary_key=True))
    protocol: str = Field(sa_column=Column(String, primary_key=True))

    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ScanledgerBridgeCursorDB(SQLModel, table=True):
    """The scanledger `/events` feed cursor last durably processed for one project."""

    __tablename__ = "scanledger_bridge_cursor"  # pyright: ignore[reportAssignmentType]

    project_id: uuid.UUID = Field(sa_column=Column(Uuid, primary_key=True))
    cursor: str = Field(sa_column=Column(String, nullable=False, server_default="0.0"))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
