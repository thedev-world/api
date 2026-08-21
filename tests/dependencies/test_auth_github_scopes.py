from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from app.config import get_settings
from app.core.session_jwt import issue_session_token
from app.dependencies.auth import get_current_developer
from fastapi import HTTPException
from tests.factories.developer_factory import make_developer


def _session_request(developer_id: UUID) -> MagicMock:
    settings = get_settings()
    token = issue_session_token(developer_id=developer_id, settings=settings)
    request = MagicMock()
    request.cookies.get.return_value = token
    return request


@pytest.mark.asyncio
async def test_get_current_developer_requires_read_org_scope() -> None:
    dev = make_developer(github_oauth_scopes="read:user,user:email")
    db = MagicMock()
    settings = get_settings()
    request = _session_request(dev.id)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=dev)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.DeveloperRepository", lambda _db: repo)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_developer(request, db, settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "github_reauth_required"


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
async def test_get_current_developer_rejects_null_scopes() -> None:
    dev = make_developer(github_oauth_scopes=None)
    db = MagicMock()
    settings = get_settings()
    request = _session_request(dev.id)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=dev)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.dependencies.auth.DeveloperRepository", lambda _db: repo)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_developer(request, db, settings)

    assert exc_info.value.detail == "github_reauth_required"
