"""Httpx launch and results endpoints: POST/GET /projects/{project_id}/scans|results/httpx."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, status

from asm_contracts.httpx_store import HttpxStoreTask
from asm_core.api.dependencies import Session
from asm_core.api.httpx.schemas import HttpxLaunchOut, HttpxResultOut, HttpxScanIn
from asm_core.api.httpx.service import list_results
from asm_core.tasks import start_httpx_scans

router = APIRouter(prefix="/projects/{project_id}")

HttpxStarter = Callable[[Sequence[HttpxStoreTask]], Awaitable[None]]


def get_httpx_starter() -> HttpxStarter:
    """The function that starts httpx runs; a dependency so tests can replace it."""
    return start_httpx_scans


@router.post("/scans/httpx", status_code=status.HTTP_202_ACCEPTED)
async def launch_httpx(
    project_id: Annotated[uuid.UUID, Path()],
    request: Annotated[HttpxScanIn, Body(embed=False)],
    start: Annotated[HttpxStarter, Depends(get_httpx_starter)],
) -> HttpxLaunchOut:
    """Starts an httpx scan over every target in the request; returns their shared scan_id."""
    scan_id = uuid.uuid4()
    tasks = [
        HttpxStoreTask(
            **request.model_dump(exclude={"targets"}),
            project_id=project_id,
            scan_id=scan_id,
            target=target,
        )
        for target in request.targets
    ]
    await start(tasks)
    return HttpxLaunchOut(scan_id=str(scan_id))


@router.get("/results/httpx")
async def read_httpx_results(
    project_id: Annotated[uuid.UUID, Path()], session: Session
) -> list[HttpxResultOut]:
    """Returns the current httpx result of every target of `project_id`."""
    return await list_results(session, project_id)
