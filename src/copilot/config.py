"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bureaucracy Copilot"
    # Example: postgresql://copilot:copilot@localhost:5432/copilot
    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
