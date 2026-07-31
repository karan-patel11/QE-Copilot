"""Application settings loaded from the environment.

ADR-0005: configuration comes from environment variables (optionally an ``.env``
file for local dev). No secrets are committed; ``.env.example`` documents every
variable. All services import the same :class:`Settings`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder signing key shipped in ``.env.example``. Production refuses to boot
# while this value is still in place (see :meth:`Settings._reject_insecure_prod`).
PLACEHOLDER_AUTH_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    """Typed application settings shared by every service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Service identity / environment
    service_name: str = Field(default="qe-copilot", alias="SERVICE_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Postgres
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="qe_copilot", alias="POSTGRES_USER")
    postgres_password: str = Field(default="qe_copilot", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="qe_copilot", alias="POSTGRES_DB")

    # Redis
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")

    # Object storage (MinIO / S3 compatible)
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="qe-copilot", alias="MINIO_BUCKET")

    # Authentication (ADR-0101/0102/0103)
    auth_secret_key: str = Field(default=PLACEHOLDER_AUTH_SECRET, alias="AUTH_SECRET_KEY")
    auth_issuer: str = Field(default="qe-copilot", alias="AUTH_ISSUER")
    auth_audience: str = Field(default="qe-copilot-api", alias="AUTH_AUDIENCE")
    auth_token_ttl_seconds: int = Field(default=3600, alias="AUTH_TOKEN_TTL_SECONDS")
    auth_dev_mode: bool = Field(default=True, alias="AUTH_DEV_MODE")
    auth_dev_admin_email: str = Field(default="admin@example.com", alias="AUTH_DEV_ADMIN_EMAIL")
    auth_dev_organisation_slug: str = Field(default="default", alias="AUTH_DEV_ORGANISATION_SLUG")

    # AI provider gateway (ADR-0201, ADR-0209). The key is read here and never
    # logged; only qe_ai_gateway consumes it (§18 L1766, §37 L2745). Absent by
    # default so the deterministic test tier runs with no credential at all —
    # an accidental live call fails loudly instead of silently billing.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    ai_model: str = Field(default="claude-opus-5", alias="AI_MODEL")
    ai_timeout_seconds: float = Field(default=120.0, alias="AI_TIMEOUT_SECONDS")
    ai_max_attempts: int = Field(default=3, alias="AI_MAX_ATTEMPTS")
    ai_max_output_tokens: int = Field(default=16_000, alias="AI_MAX_OUTPUT_TOKENS")

    # Browser origins allowed to call the API. Comma-separated; never "*", since
    # requests carry an Authorization header. The default covers local
    # development (:3000) and the Playwright server (:3100); any deployment
    # beyond localhost must set this explicitly.
    cors_allow_origins: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3100,http://127.0.0.1:3100"
        ),
        alias="CORS_ALLOW_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """``cors_allow_origins`` parsed into a list, blanks dropped."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _reject_insecure_prod(self) -> Self:
        """Fail fast rather than run production on a dev identity provider."""
        if self.environment.lower() == "production":
            if self.auth_dev_mode:
                raise ValueError("AUTH_DEV_MODE must be false when ENVIRONMENT=production")
            if self.auth_secret_key == PLACEHOLDER_AUTH_SECRET:
                raise ValueError("AUTH_SECRET_KEY must be set when ENVIRONMENT=production")
        return self

    @property
    def database_url(self) -> str:
        """Sync SQLAlchemy/psycopg URL (used by Alembic migrations)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Async SQLAlchemy/psycopg URL (used by the API readiness probe).

        psycopg3 shares one SQLAlchemy dialect (``postgresql+psycopg``) for both
        sync and async; the async engine is selected via ``create_async_engine``.
        """
        return self.database_url

    @property
    def redis_url(self) -> str:
        """Redis URL used as the Celery broker/result backend and app cache."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
