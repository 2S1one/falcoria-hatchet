from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """nuclei-worker configuration, sourced from environment variables (e.g. NUCLEI_PATH)."""

    nuclei_path: str = "nuclei"


settings = Settings()
