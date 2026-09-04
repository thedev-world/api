from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from app.services.auth_service import AuthService, _oauth_scopes_from_token_payload
from app.services.github_oauth_service import GitHubOAuthService
from app.services.score_sync_service import SYNC_COOLDOWN
from tests.factories.developer_factory import make_developer


def test_oauth_scopes_from_token_payload() -> None:
    assert _oauth_scopes_from_token_payload({"scope": "read:user,read:org"}) == "read:user,read:org"
    assert _oauth_scopes_from_token_payload({"scope": "  "}) is None
    assert _oauth_scopes_from_token_payload({}) is None


@pytest.mark.asyncio
async def test_complete_github_oauth_persists_scopes_on_existing_user() -> None:
    oauth = AsyncMock(spec=GitHubOAuthService)
    oauth.exchange_code_for_token = AsyncMock(
        return_value={"access_token": "new-token", "scope": "read:user,user:email,read:org"}
    )
    oauth.fetch_authenticated_user = AsyncMock(
        return_value={"id": 424242, "login": "testdev", "created_at": "2020-01-01T00:00:00Z"}
    )

    row = make_developer(github_oauth_scopes=None, github_token="old-token")
    db = AsyncMock()
    db.commit = AsyncMock()
    repo = AsyncMock()
    repo.get_by_github_id = AsyncMock(return_value=row)
    repo.create = AsyncMock()

    service = AuthService(oauth=oauth)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.auth_service.DeveloperRepository", lambda _db: repo)
        result = await service.complete_github_oauth(
            db,
            code="code",
            state_query="state",
            state_cookie="state",
        )

    assert result.github_token == "new-token"
    assert result.github_oauth_scopes == "read:user,user:email,read:org"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_complete_github_oauth_resets_sync_cooldown_on_token_refresh() -> None:
    oauth = AsyncMock(spec=GitHubOAuthService)
    oauth.exchange_code_for_token = AsyncMock(
        return_value={"access_token": "new-token", "scope": "read:user,user:email,read:org"}
    )
    oauth.fetch_authenticated_user = AsyncMock(
        return_value={"id": 424242, "login": "testdev", "created_at": "2020-01-01T00:00:00Z"}
    )

    recent_sync = datetime(2030, 6, 1, 12, 0, 0, tzinfo=UTC)
    row = make_developer(
        github_oauth_scopes="read:user,user:email,read:org",
        github_token="old-token",
        last_sync_at=recent_sync,
    )
    db = AsyncMock()
    db.commit = AsyncMock()
    repo = AsyncMock()
    repo.get_by_github_id = AsyncMock(return_value=row)
    repo.create = AsyncMock()

    service = AuthService(oauth=oauth)
    fixed_now = recent_sync + timedelta(minutes=5)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.auth_service.DeveloperRepository", lambda _db: repo)
        mp.setattr(
            "app.services.auth_service.datetime",
            type(
                "dt",
                (),
                {"now": staticmethod(lambda tz=None: fixed_now), "UTC": UTC},
            ),
        )
        await service.complete_github_oauth(
            db,
            code="code",
            state_query="state",
            state_cookie="state",
        )

    assert row.last_sync_at == fixed_now - SYNC_COOLDOWN - timedelta(seconds=1)


@pytest.mark.asyncio
async def test_complete_github_oauth_keeps_broader_scopes_on_re_signin() -> None:
    oauth = AsyncMock(spec=GitHubOAuthService)
    oauth.exchange_code_for_token = AsyncMock(
        return_value={"access_token": "base-token", "scope": "read:user,user:email"}
    )
    oauth.fetch_authenticated_user = AsyncMock(
        return_value={"id": 424242, "login": "testdev", "created_at": "2020-01-01T00:00:00Z"}
    )

    row = make_developer(
        github_oauth_scopes="read:user,user:email,read:org",
        github_token="org-token",
    )
    db = AsyncMock()
    db.commit = AsyncMock()
    repo = AsyncMock()
    repo.get_by_github_id = AsyncMock(return_value=row)
    repo.create = AsyncMock()

    service = AuthService(oauth=oauth)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.auth_service.DeveloperRepository", lambda _db: repo)
        result = await service.complete_github_oauth(
            db,
            code="code",
            state_query="state",
            state_cookie="state",
        )

    assert result.github_token == "org-token"
    assert result.github_oauth_scopes == "read:user,user:email,read:org"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_github_oauth_resets_sync_cooldown_on_scope_change() -> None:
    oauth = AsyncMock(spec=GitHubOAuthService)
    oauth.exchange_code_for_token = AsyncMock(
        return_value={
            "access_token": "same-token",
            "scope": "read:user,user:email,read:org,repo:read",
        }
    )
    oauth.fetch_authenticated_user = AsyncMock(
        return_value={"id": 424242, "login": "testdev", "created_at": "2020-01-01T00:00:00Z"}
    )

    recent_sync = datetime(2030, 6, 1, 12, 0, 0, tzinfo=UTC)
    row = make_developer(
        github_oauth_scopes="read:user,user:email,read:org",
        github_token="same-token",
        last_sync_at=recent_sync,
    )
    db = AsyncMock()
    db.commit = AsyncMock()
    repo = AsyncMock()
    repo.get_by_github_id = AsyncMock(return_value=row)
    repo.create = AsyncMock()

    service = AuthService(oauth=oauth)
    fixed_now = recent_sync + timedelta(minutes=5)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.auth_service.DeveloperRepository", lambda _db: repo)
        mp.setattr(
            "app.services.auth_service.datetime",
            type(
                "dt",
                (),
                {"now": staticmethod(lambda tz=None: fixed_now), "UTC": UTC},
            ),
        )
        await service.complete_github_oauth(
            db,
            code="code",
            state_query="state",
            state_cookie="state",
        )

    assert row.github_oauth_scopes == "read:user,user:email,read:org,repo:read"
    assert row.last_sync_at == fixed_now - SYNC_COOLDOWN - timedelta(seconds=1)
