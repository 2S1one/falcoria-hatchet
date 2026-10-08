from asm_contracts.httpx import HttpxScanParams, HttpxTarget
from asm_contracts.nuclei_task import ScanEnvelope


class HttpxStoreTask(ScanEnvelope):
    """Run httpx against one target with these params and store the probe as the target's current result."""

    target: HttpxTarget
    params: HttpxScanParams
