"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bureaucracy Copilot"
    # Example: postgresql://copilot:copilot@localhost:5432/copilot
    database_url: str | None = None
    # Free key from https://console.groq.com/keys - never commit it; it lives in .env only.
    groq_api_key: str | None = None
    # Models come and go; list the current ones with:  uv run python -m copilot.models
    groq_model: str = "openai/gpt-oss-120b"


@lru_cache
def get_settings() -> Settings:
    return Settings()
