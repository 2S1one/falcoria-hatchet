import pytest

from asm_nuclei_worker.config import Settings


def test_batch_defaults() -> None:
    settings = Settings()

    assert settings.batch_size == 25
    assert settings.batch_interval_seconds == 30.0


def test_batch_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NUCLEI_BATCH_SIZE", "100")
    monkeypatch.setenv("NUCLEI_BATCH_INTERVAL_SECONDS", "60")

    settings = Settings()

    assert settings.batch_size == 100
    assert settings.batch_interval_seconds == 60.0
