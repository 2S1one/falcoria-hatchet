"""Unit tests for classify_exception and its helpers, using synthetic exception chains.

httpcore chains its wrapped exceptions implicitly (__context__, from a bare except/raise with no
`from`), not explicitly (__cause__) — the tests here pin that specific behavior down, since getting it
wrong once already produced a real bug (see errors.py's docstrings).
"""

import ssl

import httpx
import pytest

from asm_contracts.httpx import ScanStatus
from asm_httpx_worker.errors import _describe, _find_ssl_error, classify_exception


def test_find_ssl_error_via_context_not_cause() -> None:
    ssl_error = ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number")
    wrapped = httpx.ConnectError("boom")
    wrapped.__context__ = ssl_error
    assert wrapped.__cause__ is None
    assert _find_ssl_error(wrapped) is ssl_error


def test_find_ssl_error_absent() -> None:
    assert _find_ssl_error(httpx.ConnectError("refused")) is None


def test_describe_falls_back_through_empty_messages_to_a_real_one() -> None:
    inner = TimeoutError()
    inner.__context__ = RuntimeError("reason: deadline exceeded")
    outer = httpx.ConnectTimeout("")
    outer.__context__ = inner
    assert _describe(outer) == "reason: deadline exceeded"


def test_describe_falls_back_to_type_name_when_everything_is_empty() -> None:
    assert _describe(TimeoutError()) == "TimeoutError"


def test_classify_wrong_version_number_is_tls_rejected() -> None:
    exc = httpx.ConnectError("boom")
    exc.__context__ = ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number")
    status, message = classify_exception(exc)
    assert status == ScanStatus.TLS_REJECTED
    assert "WRONG_VERSION_NUMBER" in message


def test_classify_other_ssl_error_is_tls_handshake_failed() -> None:
    exc = httpx.ConnectError("boom")
    exc.__context__ = ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING] eof")
    status, _ = classify_exception(exc)
    assert status == ScanStatus.TLS_HANDSHAKE_FAILED


def test_classify_connect_timeout_without_ssl_is_timeout() -> None:
    status, _ = classify_exception(httpx.ConnectTimeout(""))
    assert status == ScanStatus.TIMEOUT


def test_classify_connect_error_without_ssl_is_unreachable() -> None:
    status, message = classify_exception(httpx.ConnectError("Connection refused"))
    assert status == ScanStatus.UNREACHABLE
    assert message == "Connection refused"


def test_classify_http_error_is_request_failed() -> None:
    status, message = classify_exception(
        httpx.RemoteProtocolError("Server disconnected without sending a response.")
    )
    assert status == ScanStatus.REQUEST_FAILED
    assert message == "Server disconnected without sending a response."


def test_classify_unrecognized_exception_reraises() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        classify_exception(ValueError("unexpected"))
