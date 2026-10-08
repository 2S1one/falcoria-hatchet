"""Integration tests for probe()/runner.run() against real local servers.

Every ScanStatus value except TIMEOUT is exercised here against actual network behavior, not mocks —
this is what caught the __cause__/__context__ bug during manual testing, so it stays this way rather
than switching to mocked httpx internals. TIMEOUT isn't reproducible with a local server (see
tests/servers.py's module docstring) — it's covered by a synthetic exception test in test_errors.py
instead.
"""

import pytest
from servers import (
    closed_port,
    reset_immediately_server,
    tls_then_silent_server,
    working_http_server,
    working_tls_server,
)

from asm_contracts.httpx import (
    HttpxScanParams,
    HttpxScanResult,
    HttpxTarget,
    ScanStatus,
    Scheme,
)
from asm_httpx_worker.runner import run

pytestmark = pytest.mark.anyio

_SHORT_TIMEOUT = HttpxScanParams(http_timeout=1.0)


async def test_succeeded_on_https_first_attempt(tls_cert: tuple[str, str]) -> None:
    cert_path, key_path = tls_cert
    async with working_tls_server(cert_path, key_path) as port:
        target = HttpxTarget(target_id=1, ip="127.0.0.1", port=port)
        result = await run(target, HttpxScanParams())

    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.scheme == Scheme.HTTPS
    assert attempt.status == ScanStatus.SUCCEEDED
    assert attempt.result is not None
    assert attempt.result.status_code == 200


async def test_tls_rejected_falls_back_to_http_and_succeeds() -> None:
    async with working_http_server() as port:
        target = HttpxTarget(target_id=1, ip="127.0.0.1", port=port)
        result = await run(target, HttpxScanParams())

    assert len(result.attempts) == 2
    https_attempt, http_attempt = result.attempts
    assert https_attempt.scheme == Scheme.HTTPS
    assert https_attempt.status == ScanStatus.TLS_REJECTED
    assert http_attempt.scheme == Scheme.HTTP
    assert http_attempt.status == ScanStatus.SUCCEEDED
    assert http_attempt.result is not None
    assert http_attempt.result.status_code == 200
    assert result.is_http is True
    assert HttpxScanResult.model_validate(result.model_dump()) == result


async def test_ambiguous_tls_failure_falls_back_to_http() -> None:
    async with reset_immediately_server() as port:
        target = HttpxTarget(target_id=1, ip="127.0.0.1", port=port)
        result = await run(target, _SHORT_TIMEOUT)

    assert len(result.attempts) == 2
    https_attempt, http_attempt = result.attempts
    assert https_attempt.scheme == Scheme.HTTPS
    assert https_attempt.status == ScanStatus.TLS_HANDSHAKE_FAILED
    assert http_attempt.scheme == Scheme.HTTP
    assert http_attempt.status == ScanStatus.REQUEST_FAILED


async def test_unreachable_port_does_not_fall_back() -> None:
    async with closed_port() as port:
        target = HttpxTarget(target_id=1, ip="127.0.0.1", port=port)
        result = await run(target, _SHORT_TIMEOUT)

    assert len(result.attempts) == 1
    assert result.attempts[0].scheme == Scheme.HTTPS
    assert result.attempts[0].status == ScanStatus.UNREACHABLE
    assert result.is_http is False


async def test_request_failed_after_tls_succeeds_does_not_fall_back(
    tls_cert: tuple[str, str],
) -> None:
    cert_path, key_path = tls_cert
    async with tls_then_silent_server(cert_path, key_path) as port:
        target = HttpxTarget(target_id=1, ip="127.0.0.1", port=port)
        result = await run(target, _SHORT_TIMEOUT)

    assert len(result.attempts) == 1
    assert result.attempts[0].scheme == Scheme.HTTPS
    assert result.attempts[0].status == ScanStatus.REQUEST_FAILED
