"""Worker fleet-visibility policy: reads the active scanner workers registered with Hatchet."""

from datetime import UTC, datetime

from falcoria_tasker.hatchet.workers import active_scanners
from falcoria_tasker.workers.schemas import WorkerInfo, WorkersResponse


async def get_workers() -> WorkersResponse:
    """Lists the active scanner workers, most recently seen first."""
    workers = [
        WorkerInfo(name=worker.name, last_heartbeat_at=worker.last_heartbeat_at)
        for worker in await active_scanners()
    ]
    workers.sort(
        key=lambda w: w.last_heartbeat_at or datetime.min.replace(tzinfo=UTC), reverse=True
    )
    return WorkersResponse(workers=workers, available_workers=len(workers))
