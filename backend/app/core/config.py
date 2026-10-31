from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ABEL_",
        extra="ignore",
    )

    environment: str = "development"
    app_name: str = "ABEL Clinica"
    app_version: str = "0.2.3"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
