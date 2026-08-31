from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from app.config import get_settings
from app.core.session_jwt import issue_session_token
from app.dependencies.auth import get_current_developer
from tests.factories.developer_factory import make_developer


def _session_request(developer_id: UUID) -> MagicMock:
    settings = get_settings()
    token = issue_session_token(developer_id=developer_id, settings=settings)
    request = MagicMock()
    request.cookies.get.return_value = token
    return request


@pytest.mark.asyncio
async def test_get_current_developer_allows_basic_scopes() -> None:
    dev = make_developer(github_oauth_scopes="read:user,user:email")
    db = MagicMock()
    settings = get_settings()
    request = _session_request(dev.id)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=dev)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.DeveloperRepository", lambda _db: repo)
        result = await get_current_developer(request, db, settings)

    assert result is dev


@pytest.mark.asyncio
async def test_get_current_developer_allows_read_org_scope() -> None:
    dev = make_developer(github_oauth_scopes="read:user,user:email,read:org")
    db = MagicMock()
    settings = get_settings()
    request = _session_request(dev.id)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=dev)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.DeveloperRepository", lambda _db: repo)
        result = await get_current_developer(request, db, settings)

    assert result is dev


@pytest.mark.asyncio
async def test_get_current_developer_allows_null_scopes() -> None:
    dev = make_developer(github_oauth_scopes=None)
    db = MagicMock()
    settings = get_settings()
    request = _session_request(dev.id)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=dev)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.DeveloperRepository", lambda _db: repo)
        result = await get_current_developer(request, db, settings)

    assert result is dev
