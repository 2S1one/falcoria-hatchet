from asm_contracts.httpx import (
    HttpResult,
    HttpxScanParams,
    HttpxScanResult,
    HttpxTarget,
    ScanAttempt,
    ScanStatus,
    Scheme,
)
from asm_httpx_worker.constants import HTTP_HEADERS
from asm_httpx_worker.errors import classify_exception
from asm_httpx_worker.transport import pinned_client
from asm_httpx_worker.utils import build_url


async def probe(target: HttpxTarget, params: HttpxScanParams) -> HttpxScanResult:
    """Probe one target: attempt https first, fall back to http only on a TLS-specific failure."""
    https_attempt = await _attempt(target, params, Scheme.HTTPS)
    attempts = [https_attempt]
    if https_attempt.status in (ScanStatus.TLS_REJECTED, ScanStatus.TLS_HANDSHAKE_FAILED):
        attempts.append(await _attempt(target, params, Scheme.HTTP))
    return HttpxScanResult(target=target, attempts=attempts)


async def _attempt(target: HttpxTarget, params: HttpxScanParams, scheme: Scheme) -> ScanAttempt:
    """Make one request for one scheme and classify the outcome."""
    url = build_url(target, scheme)
    try:
        async with pinned_client(target.ip, params.http_timeout) as client:
            response = await client.get(url, headers=HTTP_HEADERS)
    except Exception as exc:
        status, error = classify_exception(exc)
        return ScanAttempt(scheme=scheme, status=status, error=error)

    result = HttpResult(
        status_code=response.status_code,
        url=url,
        headers=dict(response.headers),
        body_size=len(response.content),
    )
    return ScanAttempt(scheme=scheme, status=ScanStatus.SUCCEEDED, result=result)
