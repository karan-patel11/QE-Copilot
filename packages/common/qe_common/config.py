"""Application settings loaded from the environment.

ADR-0005: configuration comes from environment variables (optionally an ``.env``
file for local dev). No secrets are committed; ``.env.example`` documents every
variable. All services import the same :class:`Settings`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
