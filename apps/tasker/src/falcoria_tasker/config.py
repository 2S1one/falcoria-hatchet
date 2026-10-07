"""Environment-loaded settings, split by concern; import the getter you need."""

from enum import Enum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(str, Enum):
    """Deployment environment."""

    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class BaseAppSettings(BaseSettings):
    """Shared env-file location and unknown-variable policy for every settings group."""

    model_config = SettingsConfigDict(
        env_prefix="TASKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(BaseAppSettings):
    """Process-level settings: environment, debug flag, API prefix, scanledger client.

    Attributes:
        scanledger_base_url: base URL of scanledger's API (its own ``/api``
            prefix included). Env ``TASKER_SCANLEDGER_BASE_URL``.
        scanledger_token: bearer token for tasker's service account on
            scanledger — must match scanledger's own ``SCANLEDGER_TASKER_TOKEN``.
            Env ``TASKER_SCANLEDGER_TOKEN``.
        dns_resolve_semaphore_limit: max concurrent in-flight DNS lookups
            during target resolution. Env ``TASKER_DNS_RESOLVE_SEMAPHORE_LIMIT``.
        log_level: root logger level (``DEBUG``/``INFO``/``WARNING``/...). Env
            ``TASKER_LOG_LEVEL``.
    """

    env: Env = Env.LOCAL
    debug: bool = False
    api_prefix: str = "/api"
    scanledger_base_url: str
    scanledger_token: SecretStr
    dns_resolve_semaphore_limit: int = 100
    log_level: str = "INFO"


@lru_cache
def get_app_settings() -> AppSettings:
    """Returns the process settings, read from the environment on first call."""
    # pydantic-settings fills the required fields from the environment; pyright
    # only sees the synthesised __init__ and flags them as missing.
    return AppSettings()  # pyright: ignore[reportCallIssue]


class HatchetSettings(BaseAppSettings):
    """Connection settings for the Hatchet client, passed to it explicitly.

    Attributes:
        token: Hatchet API token (a JWT). Env ``TASKER_HATCHET_TOKEN``.
        host_port: engine gRPC address, ``host:port``. Env ``TASKER_HATCHET_HOST_PORT``.
        tls_strategy: client TLS strategy (``none`` for a local engine without TLS).
            Env ``TASKER_HATCHET_TLS_STRATEGY``.
    """

    model_config = SettingsConfigDict(env_prefix="TASKER_HATCHET_")

    token: SecretStr
    host_port: str
    tls_strategy: str


@lru_cache
def get_hatchet_settings() -> HatchetSettings:
    """Returns the cached Hatchet settings, read from the environment on first call."""
    # pydantic-settings fills the required fields from the environment; pyright
    # only sees the synthesised __init__ and thinks the arguments are missing.
    return HatchetSettings()  # pyright: ignore[reportCallIssue]
