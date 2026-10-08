from enum import StrEnum

from pydantic import BaseModel

from asm_contracts.httpx import HttpxTarget
from asm_contracts.nuclei_task import ScanEnvelope


class HttpxThenNucleiTask(ScanEnvelope):
    """Run httpx against `target`; if it answers over HTTP, also run nuclei against the same host:port.

    `project_id` and `scan_id` are needed only for the nuclei leg; httpx's own contract carries neither.
    """

    target: HttpxTarget


class ChainStatus(StrEnum):
    """How far one target went through the httpx-then-nuclei chain."""

    NOT_HTTP = "not_http"
    NUCLEI_STARTED = "nuclei_started"


class ChainOutcome(BaseModel):
    """What the chain did for one target; the nuclei result itself arrives through the nuclei workflow."""

    target: HttpxTarget
    status: ChainStatus
