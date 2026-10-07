"""Worker fleet-visibility endpoint."""

from fastapi import APIRouter

from falcoria_tasker.constants import Tag
from falcoria_tasker.workers import service
from falcoria_tasker.workers.schemas import WorkersResponse

router = APIRouter(tags=[Tag.WORKERS])


@router.get("")
async def get_workers() -> WorkersResponse:
    """Lists the active scanner workers registered with Hatchet."""
    return await service.get_workers()
