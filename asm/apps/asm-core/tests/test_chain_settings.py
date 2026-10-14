import pytest

from asm_core.config import ChainSettings


def test_nuclei_timeout_defaults_to_ten_minutes() -> None:
    assert ChainSettings().nuclei_timeout_seconds == 600.0


def test_nuclei_timeout_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASM_CORE_CHAIN_NUCLEI_TIMEOUT_SECONDS", "1800")

    assert ChainSettings().nuclei_timeout_seconds == 1800.0
