"""Lazy Hatchet client: connect/get/dispose, mirroring the DNS resolver's pattern.

The client is built once from HatchetSettings in the app lifespan, and route code
calls get_hatchet_client() to read it. Request handlers must use the SDK's `aio_*`
methods only — a synchronous call would block the event loop.
"""

from hatchet_sdk import ClientConfig, Hatchet
from hatchet_sdk.config import ClientTLSConfig

from falcoria_tasker.config import get_hatchet_settings


class _HatchetConnection:
    """Holds the process-wide Hatchet client once created."""

    def __init__(self) -> None:
        self.client: Hatchet | None = None


_connection = _HatchetConnection()


def connect_hatchet() -> Hatchet:
    """Builds and caches the Hatchet client from settings; call once from the lifespan."""
    settings = get_hatchet_settings()
    _connection.client = Hatchet(
        config=ClientConfig(
            token=settings.token.get_secret_value(),
            host_port=settings.host_port,
            tls_config=ClientTLSConfig(strategy=settings.tls_strategy),
        )
    )
    return _connection.client


def get_hatchet_client() -> Hatchet:
    """Returns the Hatchet client.

    Raises:
        RuntimeError: connect_hatchet() has not been called yet.
    """
    if _connection.client is None:
        raise RuntimeError("Hatchet client is not connected; call connect_hatchet() first.")
    return _connection.client


def dispose_hatchet() -> None:
    """Drops the cached client; called on application shutdown."""
    _connection.client = None
