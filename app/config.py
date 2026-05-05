from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description="Async SQLAlchemy URL (postgresql+asyncpg://...)",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")

    github_api_base: str = Field(
        default="https://api.github.com",
        description='GitHub REST API base URL (no trailing "/", e.g. https://api.github.com)',
    )
    github_token: str | None = Field(
        default=None,
        description="GitHub token (classic PAT or fine-grained) for higher rate limits",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
