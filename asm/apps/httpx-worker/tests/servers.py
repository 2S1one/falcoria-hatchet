"""Real local TCP/TLS servers backing the probe.py integration tests, not tests themselves.

No server here reproduces ScanStatus.TIMEOUT: a genuine TCP-connect-level timeout needs packets actually
dropped (firewall/network level) — any server that calls listen() lets the OS complete the TCP handshake
instantly regardless of whether the app ever calls accept(). That classification is locked in instead by
the synthetic exception test in test_errors.py.
"""

import asyncio
import ssl
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Coroutine[None, None, None]]

_OK_RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"


async def _respond_ok(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    await reader.read(4096)
    writer.write(_OK_RESPONSE)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _reset_immediately(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    with suppress(TimeoutError, OSError):
        await asyncio.wait_for(reader.read(4096), timeout=2.0)
    writer.close()
    await writer.wait_closed()


@asynccontextmanager
async def _serve(handler: Handler, ssl_context: ssl.SSLContext | None = None) -> AsyncIterator[int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=ssl_context)
    port = server.sockets[0].getsockname()[1]
    async with server:
        task = asyncio.create_task(server.serve_forever())
        try:
            yield port
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def working_http_server() -> AbstractAsyncContextManager[int]:
    """Plain HTTP, responds 200 to anything — the succeeded-on-http case."""
    return _serve(_respond_ok)


def reset_immediately_server() -> AbstractAsyncContextManager[int]:
    """Accepts TCP, reads whatever's sent, closes with no response.

    Against an HTTPS attempt this looks like a mid-handshake reset (tls_handshake_failed); against a
    plain HTTP attempt it's request_failed — the same server exercises both, depending on which scheme
    the caller attempts against it.
    """
    return _serve(_reset_immediately)


def working_tls_server(cert_path: str, key_path: str) -> AbstractAsyncContextManager[int]:
    """Completes a real TLS handshake, then responds 200 — the succeeded-on-https case."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return _serve(_respond_ok, ctx)


def tls_then_silent_server(cert_path: str, key_path: str) -> AbstractAsyncContextManager[int]:
    """Completes a real TLS handshake, then closes with no HTTP response — request_failed, no fallback."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return _serve(_reset_immediately, ctx)


@asynccontextmanager
async def closed_port() -> AsyncIterator[int]:
    """A port nothing is listening on — the unreachable case."""
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()
    yield port
