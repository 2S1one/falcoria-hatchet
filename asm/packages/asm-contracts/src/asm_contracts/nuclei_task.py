import hashlib
import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from asm_contracts.common import ScannerName
from asm_contracts.nuclei import NucleiFinding, NucleiScanParams, NucleiTarget


class ScanEnvelope(BaseModel):
    """Business identity shared across scanner tasks that need it; not every scanner does."""

    project_id: uuid.UUID
    scan_id: uuid.UUID


class NucleiScanStatus(StrEnum):
    """Outcome of one nuclei scan, as reported to the caller of its target."""

    SUCCESS = "success"
    ERROR = "error"


class NucleiScanTask(ScanEnvelope):
    """One nuclei scan task, for one target; `batch_key` decides which targets share a batch."""

    target: NucleiTarget
    params: NucleiScanParams
    timeout: float = Field(default=600.0, gt=0, le=86400)

    @computed_field
    @property
    def batch_key(self) -> str:
        """Group key: tasks with the same project, scan, params and timeout are scanned together."""
        payload = f"{self.params.model_dump_json()}|{self.timeout}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{self.project_id}-{self.scan_id}-{digest}"


class NucleiScanResult(BaseModel):
    """Answer for one target: its findings on success, the error text otherwise."""

    scanner: Literal[ScannerName.NUCLEI] = ScannerName.NUCLEI
    target: NucleiTarget
    status: NucleiScanStatus
    findings: list[NucleiFinding] = Field(
        default_factory=list, description="Empty unless `status` is `SUCCESS`."
    )
    error: str | None = Field(default=None, description="Set only when `status` is `ERROR`.")
