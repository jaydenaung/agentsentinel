"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object — all values come from .env or environment."""

    database_url: str = "postgresql+asyncpg://REDACTED@localhost:5432/agentsentinel"
    redis_url: str = "redis://localhost:6379/0"
    slack_webhook_url: str | None = None
    secret_key: str = "dev-secret-key-change-in-production"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
