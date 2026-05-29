from functools import lru_cache
from typing import Self

from pydantic import Field, computed_field, field_validator, model_validator
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

    github_oauth_client_id: str = Field(
        ...,
        description="GitHub OAuth App client ID",
    )
    github_oauth_client_secret: str = Field(
        ...,
        description="GitHub OAuth App client secret",
    )
    oauth_callback_url: str = Field(
        ...,
        description=(
            "Exact Authorization callback URL registered on the GitHub OAuth app "
            "(e.g. http://localhost:8000/api/v1/auth/github/callback or same path behind a proxy)"
        ),
    )
    allowed_frontend_origins: str = Field(
        default="http://localhost:3000",
        description=(
            "Comma-separated browser origins: CORS allowlist and post-login redirect allowlist"
        ),
    )
    oauth_post_login_redirect: str = Field(
        default="",
        description=(
            "URL after successful GitHub OAuth (prefix must match an allowed origin). "
            "If empty, uses first allowed origin + /"
        ),
    )
    jwt_secret_key: str = Field(
        ...,
        min_length=32,
        description="HMAC secret for session JWT (use a long random string in production)",
    )
    jwt_expires_seconds: int = Field(
        default=60 * 60 * 24 * 7,
        ge=60,
        description="Session cookie lifetime in seconds",
    )
    jwt_algorithm: str = Field(default="HS256")
    session_cookie_name: str = Field(default="devplanet_session")
    session_cookie_secure: bool = Field(
        default=False,
        description="Set Secure flag on session cookie (use True behind HTTPS in production)",
    )
    oauth_state_cookie_name: str = Field(default="github_oauth_state")
    oauth_state_max_age_seconds: int = Field(default=600, ge=60, le=3600)

    s3_endpoint_url: str = Field(
        default="http://localhost:9000",
        description=("S3-compatible endpoint URL. Scaleway in prod, MinIO in local dev."),
    )
    s3_access_key: str = Field(
        description="S3 access key (Scaleway SCW_ACCESS_KEY or MinIO MINIO_ROOT_USER)",
    )
    s3_secret_key: str = Field(
        description="S3 secret key (Scaleway SCW_SECRET_KEY or MinIO MINIO_ROOT_PASSWORD)",
    )
    s3_bucket_name: str = Field(
        default="devplanet",
        description="Bucket name that holds the planet-data.json file",
    )
    s3_region: str = Field(
        default="us-east-1",
        description="S3 region (use Scaleway region in prod, e.g. nl-ams)",
    )
    s3_planet_json_key: str = Field(
        default="planet-data.json",
        description="Object key for the planet snapshot file in the bucket",
    )
    s3_public_base_url: str = Field(
        default="",
        description=(
            "Public base URL for S3 objects served to browsers "
            "(e.g. CDN URL or http://localhost:9000 for MinIO in Docker). "
            "If empty, falls back to s3_endpoint_url."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_s3_public_base_url(self) -> str:
        explicit = self.s3_public_base_url.strip().rstrip("/")
        if explicit:
            return explicit
        return self.s3_endpoint_url.rstrip("/")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def planet_json_url(self) -> str:
        base = self.effective_s3_public_base_url
        return f"{base}/{self.s3_bucket_name}/{self.s3_planet_json_key}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_frontend_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_post_login_redirect(self) -> str:
        explicit = self.oauth_post_login_redirect.strip()
        if explicit:
            return explicit
        first = self.cors_origins[0].rstrip("/")
        return f"{first}/"

    @field_validator("allowed_frontend_origins")
    @classmethod
    def normalize_origins(cls, v: str) -> str:
        parts = [o.strip() for o in v.split(",") if o.strip()]
        if not parts:
            raise ValueError("allowed_frontend_origins must contain at least one origin")
        return ",".join(parts)

    @field_validator("oauth_post_login_redirect")
    @classmethod
    def strip_post_login(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def post_login_under_allowlist(self) -> Self:
        explicit = self.oauth_post_login_redirect.strip()
        if explicit and not self.is_redirect_url_allowed(explicit):
            raise ValueError(
                "oauth_post_login_redirect must match allowed_frontend_origins prefix",
            )
        return self

    def is_redirect_url_allowed(self, url: str) -> bool:
        u = url.strip()
        if not u:
            return False
        for origin in self.cors_origins:
            o = origin.rstrip("/")
            if u == o or u.startswith(f"{o}/"):
                return True
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
