"""HTTP client for the access checks the API delegates to scanledger."""

from enum import Enum, auto
from functools import lru_cache
from uuid import UUID

import httpx

from asm_core.config import get_scanledger_settings


class AccessResult(Enum):
    """Outcome of a scanledger access check."""

    OK = auto()
    UNAUTHORIZED = auto()
    FORBIDDEN = auto()
    NOT_FOUND = auto()


class ScanledgerAccessClient:
    """Thin wrapper over the scanledger project endpoint used as an access check."""

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, transport=transport)

    async def aclose(self) -> None:
        """Closes the underlying HTTP connection pool."""
        await self._client.aclose()

    async def check_access(self, token: str, project_id: UUID) -> AccessResult:
        """Checks whether `token` is valid and a member of `project_id`.

        Relays `token` as-is to scanledger's own project endpoint, so scanledger's
        auth gating stays the single source of truth.
        """
        response = await self._client.get(
            f"/projects/{project_id}", headers={"Authorization": f"Bearer {token}"}
        )
        if response.status_code == httpx.codes.OK:
            return AccessResult.OK
        if response.status_code == httpx.codes.UNAUTHORIZED:
            return AccessResult.UNAUTHORIZED
        if response.status_code == httpx.codes.FORBIDDEN:
            return AccessResult.FORBIDDEN
        if response.status_code == httpx.codes.NOT_FOUND:
            return AccessResult.NOT_FOUND
        response.raise_for_status()
        msg = f"Unexpected scanledger response: {response.status_code}."
        raise httpx.HTTPStatusError(msg, request=response.request, response=response)


@lru_cache
def get_scanledger_access_client() -> ScanledgerAccessClient:
    """Returns the process-wide scanledger access client, built on first use."""
    return ScanledgerAccessClient(get_scanledger_settings().api_url)


async def dispose_scanledger_access_client() -> None:
    """Closes the client's connection pool; called on application shutdown."""
    if get_scanledger_access_client.cache_info().currsize:
        await get_scanledger_access_client().aclose()
