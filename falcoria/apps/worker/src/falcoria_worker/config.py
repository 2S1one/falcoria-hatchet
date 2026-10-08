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
        env_prefix="WORKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(BaseAppSettings):
    """Process-level settings shared by the scanner and the uploader.

    Attributes:
        nmap_path: path to the nmap executable (scanner only). Env ``WORKER_NMAP_PATH``.
        command_grace_period_seconds: how long to wait after SIGTERM before escalating
            a scan subprocess to SIGKILL. Env ``WORKER_COMMAND_GRACE_PERIOD_SECONDS``.
        log_level: root logger level (``DEBUG``/``INFO``/``WARNING``/...). Env
            ``WORKER_LOG_LEVEL``.
    """

    env: Env = Env.LOCAL
    debug: bool = False
    nmap_path: str = "nmap"
    command_grace_period_seconds: float = 5.0
    log_level: str = "INFO"


@lru_cache
def get_app_settings() -> AppSettings:
    """Returns the process settings, read from the environment on first call."""
    return AppSettings()


class HatchetSettings(BaseAppSettings):
    """Connection settings for the Hatchet client, passed to it explicitly.

    Attributes:
        token: Hatchet API token (a JWT). Env ``WORKER_HATCHET_TOKEN``.
        host_port: engine gRPC address, ``host:port``. Env ``WORKER_HATCHET_HOST_PORT``.
        tls_strategy: client TLS strategy (``none`` for a local engine without TLS).
            Env ``WORKER_HATCHET_TLS_STRATEGY``.
    """

    model_config = SettingsConfigDict(env_prefix="WORKER_HATCHET_")

    token: SecretStr
    host_port: str
    tls_strategy: str


@lru_cache
def get_hatchet_settings() -> HatchetSettings:
    """Returns the cached Hatchet settings, read from the environment on first call."""
    # pydantic-settings fills the required fields from the environment; pyright
    # only sees the synthesised __init__ and thinks the arguments are missing.
    return HatchetSettings()  # pyright: ignore[reportCallIssue]


class ScanledgerSettings(BaseAppSettings):
    """Connection settings for scanledger (uploader only).

    Attributes:
        base_url: base URL of scanledger's API. Env ``WORKER_SCANLEDGER_BASE_URL``.
        token: bearer token for the worker's service account on scanledger. Env
            ``WORKER_SCANLEDGER_TOKEN``.
        tls_verify: whether to verify scanledger's TLS certificate; false only for local
            insecure testing. Env ``WORKER_SCANLEDGER_TLS_VERIFY``.
    """

    model_config = SettingsConfigDict(env_prefix="WORKER_SCANLEDGER_")

    base_url: str
    token: SecretStr
    tls_verify: bool = True


@lru_cache
def get_scanledger_settings() -> ScanledgerSettings:
    """Returns the cached scanledger settings, read from the environment on first call."""
    # pydantic-settings fills the required fields from the environment; pyright
    # only sees the synthesised __init__ and thinks the arguments are missing.
    return ScanledgerSettings()  # pyright: ignore[reportCallIssue]
