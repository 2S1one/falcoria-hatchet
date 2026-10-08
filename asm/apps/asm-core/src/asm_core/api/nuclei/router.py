"""Nuclei launch and results endpoints: POST/GET /projects/{project_id}/scans|results/nuclei."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, status

from asm_contracts.nuclei_task import NucleiScanTask
from asm_core.api.dependencies import Session
from asm_core.api.nuclei.schemas import NucleiFindingOut, NucleiLaunchOut, NucleiScanIn
from asm_core.api.nuclei.service import list_findings
from asm_core.tasks import start_nuclei_scans

router = APIRouter(prefix="/projects/{project_id}")

NucleiStarter = Callable[[Sequence[NucleiScanTask]], Awaitable[None]]


def get_nuclei_starter() -> NucleiStarter:
    """The function that starts nuclei runs; a dependency so tests can replace it."""
    return start_nuclei_scans


@router.post("/scans/nuclei", status_code=status.HTTP_202_ACCEPTED)
async def launch_nuclei(
    project_id: Annotated[uuid.UUID, Path()],
    request: Annotated[NucleiScanIn, Body(embed=False)],
    start: Annotated[NucleiStarter, Depends(get_nuclei_starter)],
) -> NucleiLaunchOut:
    """Starts a nuclei scan over every target in the request; returns their shared scan_id."""
    scan_id = uuid.uuid4()
    tasks = [
        NucleiScanTask(
            **request.model_dump(exclude={"targets"}),
            project_id=project_id,
            scan_id=scan_id,
            target=target,
        )
        for target in request.targets
    ]
    await start(tasks)
    return NucleiLaunchOut(scan_id=str(scan_id))


@router.get("/results/nuclei")
async def read_nuclei_results(
    project_id: Annotated[uuid.UUID, Path()], session: Session
) -> list[NucleiFindingOut]:
    """Returns every currently-active nuclei finding for `project_id`."""
    return await list_findings(session, project_id)
