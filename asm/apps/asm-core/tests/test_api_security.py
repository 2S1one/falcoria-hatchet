import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from asm_core.api import security
from asm_core.api.scanledger_access import ScanledgerAccessClient
from asm_core.api.security import clear_access_cache, require_project_access

_PROJECT = uuid.UUID("00000000-0000-0000-0000-000000000001")
_URL = f"/projects/{_PROJECT}/ping"
_BEARER = {"Authorization": "Bearer caller-token"}


class _Scanledger:
    """Stands in for scanledger: records the checks and answers with a fixed status."""

    def __init__(self) -> None:
        self.status = 200
        self.unreachable = False
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.unreachable:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(self.status)


@pytest.fixture
def scanledger(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Scanledger]:
    fake = _Scanledger()
    client = ScanledgerAccessClient("http://scanledger.test", httpx.MockTransport(fake))
    monkeypatch.setattr(security, "get_scanledger_access_client", lambda: client)
    clear_access_cache()
    yield fake
    clear_access_cache()


@pytest.fixture
def client(scanledger: _Scanledger) -> TestClient:
    app = FastAPI()

    @app.get("/projects/{project_id}/ping", dependencies=[Depends(require_project_access)])
    async def ping(project_id: uuid.UUID) -> dict[str, str]:
        return {"project_id": str(project_id)}

    return TestClient(app)


def test_valid_member_passes_and_token_is_relayed_to_the_project_endpoint(
    client: TestClient, scanledger: _Scanledger
) -> None:
    response = client.get(_URL, headers=_BEARER)

    assert response.status_code == 200
    (request,) = scanledger.requests
    assert request.url.path == f"/projects/{_PROJECT}"
    assert request.headers["Authorization"] == "Bearer caller-token"


def test_missing_token_is_401_without_calling_scanledger(
    client: TestClient, scanledger: _Scanledger
) -> None:
    response = client.get(_URL)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert scanledger.requests == []


@pytest.mark.parametrize("status", [401, 403, 404])
def test_scanledger_refusal_is_passed_through(
    client: TestClient, scanledger: _Scanledger, status: int
) -> None:
    scanledger.status = status

    assert client.get(_URL, headers=_BEARER).status_code == status


def test_unreachable_scanledger_is_503_not_access(
    client: TestClient, scanledger: _Scanledger
) -> None:
    scanledger.unreachable = True

    assert client.get(_URL, headers=_BEARER).status_code == 503


def test_unexpected_scanledger_status_is_503(client: TestClient, scanledger: _Scanledger) -> None:
    scanledger.status = 500

    assert client.get(_URL, headers=_BEARER).status_code == 503


def test_repeat_check_within_ttl_is_served_from_cache(
    client: TestClient, scanledger: _Scanledger
) -> None:
    client.get(_URL, headers=_BEARER)
    client.get(_URL, headers=_BEARER)

    assert len(scanledger.requests) == 1


def test_cache_is_per_token(client: TestClient, scanledger: _Scanledger) -> None:
    client.get(_URL, headers=_BEARER)
    client.get(_URL, headers={"Authorization": "Bearer other-token"})

    assert len(scanledger.requests) == 2
