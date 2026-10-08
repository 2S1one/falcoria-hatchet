from pydantic import BaseModel

from asm_contracts.nuclei_task import NucleiScanResult, NucleiScanTask


class PersistNucleiInput(BaseModel):
    """One target's nuclei task and its answer, sent to be stored."""

    task: NucleiScanTask
    result: NucleiScanResult


class PersistNucleiOutput(BaseModel):
    """Acknowledgement of a nuclei persist call."""

    stored: bool
    findings: int
