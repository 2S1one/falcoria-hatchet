from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from asm_contracts.nuclei import NucleiScanParams


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings for the asm-core database."""

    model_config = SettingsConfigDict(env_prefix="ASM_CORE_DB_", extra="ignore")

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    name: str
    echo: bool = False


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """Returns the cached database settings, read from the environment on first call."""
    # pydantic-settings fills the required fields from the environment; pyright only
    # sees the synthesised __init__ and thinks the arguments are missing.
    return DatabaseSettings()  # pyright: ignore[reportCallIssue]


class ScanledgerSettings(BaseSettings):
    """HTTP client settings for calling scanledger's event feed."""

    model_config = SettingsConfigDict(env_prefix="SCANLEDGER_", extra="ignore")

    api_url: str
    asm_token: SecretStr


@lru_cache
def get_scanledger_settings() -> ScanledgerSettings:
    """Returns the cached scanledger client settings, read from the environment on first call."""
    return ScanledgerSettings()  # pyright: ignore[reportCallIssue]


class ChainSettings(BaseSettings):
    """Scan parameters the httpx-then-nuclei chain uses for the nuclei leg.

    Env `ASM_CORE_CHAIN_NUCLEI_PARAMS` takes a JSON object of `NucleiScanParams` fields, e.g.
    `{"templates": ["/opt/nuclei-templates/http/technologies"], "rate_limit": 20}`; unset means nuclei's
    own defaults.
    """

    model_config = SettingsConfigDict(env_prefix="ASM_CORE_CHAIN_", extra="ignore")

    nuclei_params: NucleiScanParams = Field(default_factory=NucleiScanParams)


@lru_cache
def get_chain_settings() -> ChainSettings:
    """Returns the cached chain settings, read from the environment on first call."""
    return ChainSettings()
