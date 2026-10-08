from asm_contracts.httpx import HttpxScanParams, HttpxScanResult, HttpxTarget
from asm_httpx_worker.probe import probe


async def run(target: HttpxTarget, params: HttpxScanParams) -> HttpxScanResult:
    """Entry point for the httpx scanner — the one function the Hatchet task calls."""
    return await probe(target, params)
