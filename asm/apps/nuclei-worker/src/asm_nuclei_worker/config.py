from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """nuclei-worker configuration, sourced from environment variables (e.g. NUCLEI_PATH).

    `NUCLEI_BATCH_SIZE` and `NUCLEI_BATCH_INTERVAL_SECONDS` are read when the worker starts, so a
    change needs a container restart, not an image rebuild.
    """

    nuclei_path: str = "nuclei"
    batch_size: int = Field(
        default=25,
        ge=1,
        validation_alias="NUCLEI_BATCH_SIZE",
        description="Targets cut into one nuclei process.",
    )
    batch_interval_seconds: float = Field(
        default=30.0,
        gt=0,
        validation_alias="NUCLEI_BATCH_INTERVAL_SECONDS",
        description="A partial batch starts after this long without a flush.",
    )


settings = Settings()
