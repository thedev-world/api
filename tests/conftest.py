from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

_ENV_DEFAULTS: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://devplanet:devplanet@127.0.0.1:5432/devplanet",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "CELERY_BROKER_URL": "redis://127.0.0.1:6379/0",
    "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/0",
    "GITHUB_OAUTH_CLIENT_ID": "test-oauth-client-id",
    "GITHUB_OAUTH_CLIENT_SECRET": "test-oauth-client-secret",
    "OAUTH_CALLBACK_URL": "http://test/api/v1/auth/github/callback",
    "ALLOWED_FRONTEND_ORIGINS": "http://localhost:3000,http://test",
    "S3_ACCESS_KEY": "devplanet",
    "S3_SECRET_KEY": "devplanet",
    "JWT_SECRET_KEY": "unit-test-jwt-secret-key-32-bytes-min",
    "TOKEN_ENCRYPTION_KEY": "UaFsQc-_TszKnclBK2EtbZy_-i88lwSAXRC1Cd4-kA0=",
}


def _load_env() -> None:
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


_load_env()

import pytest
from app.database import get_db
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _mock_db_session_that_succeeds() -> AsyncGenerator[AsyncSession, None]:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    yield session  # type: ignore[misc]


async def _mock_db_session_that_fails() -> AsyncGenerator[AsyncSession, None]:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=RuntimeError("database unavailable"))
    yield session  # type: ignore[misc]


@pytest.fixture
def override_db_healthy() -> None:
    app.dependency_overrides[get_db] = _mock_db_session_that_succeeds


@pytest.fixture
def override_db_unhealthy() -> None:
    app.dependency_overrides[get_db] = _mock_db_session_that_fails
