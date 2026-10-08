import ssl

import httpx

from asm_contracts.httpx import ScanStatus

_SSL_WRONG_VERSION_NUMBER = "WRONG_VERSION_NUMBER"


def classify_exception(exc: Exception) -> tuple[ScanStatus, str]:
    """Map a request exception to a ScanStatus, telling definite TLS rejection apart from other failures.

    A connect-level SSLError whose text contains "WRONG_VERSION_NUMBER" means the peer answered a TLS
    ClientHello with plaintext — a certain "not TLS" signal, distinct from every other TLS failure mode
    (timeout, protocol mismatch, reset), which is ambiguous and gets its own status. Absent an SSLError,
    ConnectTimeout and ConnectError are kept separate: an immediate refusal (ConnectError) means nothing
    is listening, while a timeout (ConnectTimeout) means something accepted the TCP connection but never
    answered — httpx doesn't expose which phase (TCP connect vs. TLS handshake) actually timed out, but
    the exception class alone already tells "definitely closed" apart from "silent, cause unknown". An
    exception type this function doesn't recognize is re-raised rather than guessed at, so an
    unanticipated failure mode surfaces as a bug instead of a silently wrong status.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        ssl_error = _find_ssl_error(exc)
        if ssl_error is not None:
            if _SSL_WRONG_VERSION_NUMBER in str(ssl_error):
                return ScanStatus.TLS_REJECTED, str(ssl_error)
            return ScanStatus.TLS_HANDSHAKE_FAILED, str(ssl_error)
        if isinstance(exc, httpx.ConnectTimeout):
            return ScanStatus.TIMEOUT, _describe(exc)
        return ScanStatus.UNREACHABLE, _describe(exc)
    if isinstance(exc, httpx.HTTPError):
        return ScanStatus.REQUEST_FAILED, _describe(exc)
    raise exc


def _find_ssl_error(exc: BaseException) -> ssl.SSLError | None:
    """Walk the cause/context chain for the underlying SSLError.

    httpcore wraps the SSLError implicitly (an `except`-block re-raise with no `from`, which Python
    records as `__context__`, not `__cause__`) — both must be checked, `__cause__` isn't enough.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return current
        current = current.__cause__ or current.__context__
    return None


def _describe(exc: BaseException) -> str:
    """First non-empty message found while walking cause/context, or the exception's type name.

    A bare `TimeoutError()` carries no message by design, but a wrapped/underlying exception further
    down the chain often does (e.g. anyio's CancelledError explains which deadline was exceeded) —
    str(exc) alone can silently be empty.
    """
    current: BaseException | None = exc
    while current is not None:
        text = str(current)
        if text:
            return text
        current = current.__cause__ or current.__context__
    return type(exc).__name__
