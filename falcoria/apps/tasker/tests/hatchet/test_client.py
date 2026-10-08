import base64
import json
from typing import Any

import pytest
from pydantic import SecretStr

from falcoria_tasker.config import HatchetSettings
from falcoria_tasker.hatchet import client


def _jwt() -> str:
    """Builds an unsigned token with the claims the SDK reads from it."""
    claims = {
        "sub": "tenant-1",
        "server_url": "http://localhost:8080",
        "grpc_broadcast_address": "localhost:7077",
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii")
    return f"ey.{payload}.sig"


_TOKEN = _jwt()


class _FakeHatchet:
    def __init__(self, config: Any) -> None:
        self.config = config


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    client.dispose_hatchet()


def test_get_before_connect_raises() -> None:
    with pytest.raises(RuntimeError):
        client.get_hatchet_client()


def test_connect_passes_settings_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = HatchetSettings.model_construct(
        token=SecretStr(_TOKEN), host_port="localhost:7077", tls_strategy="none"
    )
    monkeypatch.setattr(client, "get_hatchet_settings", lambda: settings)
    monkeypatch.setattr(client, "Hatchet", _FakeHatchet)

    connected = client.connect_hatchet()

    assert client.get_hatchet_client() is connected
    config = connected.config  # pyright: ignore[reportAttributeAccessIssue]
    assert config.token == _TOKEN
    assert config.host_port == "localhost:7077"
    assert config.tls_config.strategy == "none"


def test_dispose_clears_client(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = HatchetSettings.model_construct(
        token=SecretStr(_TOKEN), host_port="localhost:7077", tls_strategy="none"
    )
    monkeypatch.setattr(client, "get_hatchet_settings", lambda: settings)
    monkeypatch.setattr(client, "Hatchet", _FakeHatchet)
    client.connect_hatchet()

    client.dispose_hatchet()

    with pytest.raises(RuntimeError):
        client.get_hatchet_client()
