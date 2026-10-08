from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from hatchet_sdk.clients.rest.models.worker_status import WorkerStatus

from falcoria_contracts.scan_names import ROLE_SCANNER, ROLE_UPLOADER, WORKER_ROLE_LABEL
from falcoria_tasker.hatchet import workers as hatchet_workers
from falcoria_tasker.workers import service

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _worker(
    name: str, status: WorkerStatus, heartbeat: datetime | None, role: str = ROLE_SCANNER
) -> Any:
    return SimpleNamespace(
        name=name,
        status=status,
        last_heartbeat_at=heartbeat,
        labels=[SimpleNamespace(key=WORKER_ROLE_LABEL, value=role)],
    )


def _patch_workers(monkeypatch: pytest.MonkeyPatch, rows: list[Any]) -> None:
    async def aio_list() -> Any:
        return SimpleNamespace(rows=rows)

    client = SimpleNamespace(workers=SimpleNamespace(aio_list=aio_list))
    monkeypatch.setattr(hatchet_workers, "get_hatchet_client", lambda: client)


async def test_get_workers_lists_only_active_scanners(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_workers(
        monkeypatch,
        [
            _worker("a_1.1.1.1", WorkerStatus.ACTIVE, NOW),
            _worker("b_2.2.2.2", WorkerStatus.INACTIVE, NOW),
            _worker("host_uploader", WorkerStatus.ACTIVE, NOW, role=ROLE_UPLOADER),
        ],
    )

    response = await service.get_workers()

    assert [w.name for w in response.workers] == ["a_1.1.1.1"]
    assert response.available_workers == 1


async def test_get_workers_sorts_most_recently_seen_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_workers(
        monkeypatch,
        [
            _worker("old", WorkerStatus.ACTIVE, NOW - timedelta(minutes=5)),
            _worker("never", WorkerStatus.ACTIVE, None),
            _worker("new", WorkerStatus.ACTIVE, NOW),
        ],
    )

    response = await service.get_workers()

    assert [w.name for w in response.workers] == ["new", "old", "never"]


async def test_get_workers_is_empty_without_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_workers(monkeypatch, [])

    response = await service.get_workers()

    assert response.workers == []
    assert response.available_workers == 0
