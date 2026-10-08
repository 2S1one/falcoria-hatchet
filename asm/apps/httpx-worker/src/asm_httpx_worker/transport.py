import ssl
from collections.abc import Iterable

import httpcore
import httpx
from httpcore import SOCKET_OPTION, AnyIOBackend


class _IPPinnedBackend(httpcore.AsyncNetworkBackend):
    """Network backend that ignores whatever host httpcore resolves and always connects to `ip`.

    httpx's normal path does DNS resolution based on the URL's host; overriding `connect_tcp` here is
    the only way to force the connection to a known IP while still presenting a different Host header/SNI
    inside that connection (see utils.build_url). The other two methods aren't part of pinning — they
    exist only because AsyncNetworkBackend requires them, and they pass straight through unchanged.
    """

    def __init__(self, ip: str):
        self._ip = ip
        self._backend = AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,  # unused: httpcore's AsyncNetworkBackend interface requires it, always self._ip instead
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_tcp(
            self._ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


def pinned_client(ip: str, timeout: float) -> httpx.AsyncClient:
    """Build an httpx client that connects to `ip` regardless of the URL's host, TLS unverified."""
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    pool = httpcore.AsyncConnectionPool(
        ssl_context=ssl_ctx,
        network_backend=_IPPinnedBackend(ip),
    )
    transport = httpx.AsyncHTTPTransport()
    transport._pool = pool

    return httpx.AsyncClient(transport=transport, follow_redirects=False, timeout=timeout)
