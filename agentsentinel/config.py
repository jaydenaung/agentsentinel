"""Application settings loaded from environment variables."""

import warnings
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_SECRET = "dev-secret-key-change-in-production"


class Settings(BaseSettings):
    """Central settings object — all values come from .env or environment."""

    database_url: str = "postgresql+asyncpg://REDACTED@localhost:5432/agentsentinel"
    redis_url: str = "redis://localhost:6379/0"
    slack_webhook_url: str | None = None
    secret_key: str = WEAK_SECRET
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Set SENTINEL_ALLOW_WEAK_SECRET=true in dev/test to suppress the startup refusal
    # when SECRET_KEY is the insecure default. Never set this in production.
    allow_weak_secret: bool = False

    # Set SHOW_DOCS=true to enable /docs, /redoc, /openapi.json.
    # Disabled by default — the OpenAPI schema is a reconnaissance resource.
    show_docs: bool = False

    # Optional path for secure bootstrap key delivery.
    # When set, the plaintext bootstrap admin key is written to this file (mode 0600)
    # instead of being printed to stderr. Use a mounted secrets volume in production:
    #   BOOTSTRAP_KEY_FILE=/run/secrets/bootstrap-key
    bootstrap_key_file: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if v == WEAK_SECRET:
            warnings.warn(
                "SECRET_KEY is the insecure default. Set a random SECRET_KEY before deploying.",
                stacklevel=2,
            )
        return v

    @field_validator("slack_webhook_url")
    @classmethod
    def validate_slack_url(cls, v: str | None) -> str | None:
        """Prevent SSRF — only allow HTTPS calls to hooks.slack.com."""
        if v is None:
            return v
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("SLACK_WEBHOOK_URL must use HTTPS")
        if not (parsed.netloc == "hooks.slack.com" or parsed.netloc.endswith(".hooks.slack.com")):
            raise ValueError("SLACK_WEBHOOK_URL must point to hooks.slack.com")
        return v

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_origins(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError('cors_origins must not contain "*" — specify explicit origins')
        return v


settings = Settings()
