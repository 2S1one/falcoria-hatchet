"""Builds the Hatchet client from settings, passed to it explicitly."""

from hatchet_sdk import ClientConfig, Hatchet
from hatchet_sdk.config import ClientTLSConfig

from falcoria_worker.config import get_hatchet_settings


def build_hatchet() -> Hatchet:
    """Creates the Hatchet client from HatchetSettings."""
    settings = get_hatchet_settings()
    return Hatchet(
        config=ClientConfig(
            token=settings.token.get_secret_value(),
            host_port=settings.host_port,
            tls_config=ClientTLSConfig(strategy=settings.tls_strategy),
        )
    )
