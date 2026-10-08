"""Worker fleet-visibility response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class WorkerInfo(BaseModel):
    """One active scanner worker process registered with Hatchet."""

    name: str = Field(description="hostname_external_ip, as reported by the worker.")
    last_heartbeat_at: datetime | None = Field(description="Most recent heartbeat, or None.")


class WorkersResponse(BaseModel):
    """The active scanner worker fleet."""

    workers: list[WorkerInfo]
    available_workers: int
