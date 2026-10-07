import re

import pytest

from falcoria_worker import main

_HATCHET_NAME = re.compile(r"^[a-zA-Z0-9.\-_]+$")


def test_worker_name_is_valid_for_hatchet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.socket, "gethostname", lambda: "scan host:1")

    name = main.worker_name("192.0.2.10")

    assert name == "scan-host-1_192.0.2.10"
    assert _HATCHET_NAME.match(name)
