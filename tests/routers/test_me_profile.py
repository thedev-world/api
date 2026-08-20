import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.dependencies.auth import get_current_developer
from app.dependencies.providers import get_developer_service
from app.domain.island import IslandChoice
from app.main import app
from app.models.developer import Developer


def _sample_developer() -> Developer:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return Developer(
        id=uuid.UUID("00000000-0000-4000-8000-000000000042"),
        github_id=42,
        github_login="alice",
        commits_alltime=1,
        commits_breakdown_sum=0,
        commits_farm_flagged=False,
        commits_farm_cleared=False,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        forks_received=0,
        followers=0,
        stars_received_raw=3,
        stars_received_capped=3,
        owned_non_fork_repos_count=1,
        account_created_at=now,
        xp_brut=100,
        last_sync_at=now,
        island=None,
        is_onboarded=False,
        avatar_url=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def _logged_in_alice() -> None:
    alice = _sample_developer()

    async def _dev() -> Developer:
        return alice

    app.dependency_overrides[get_current_developer] = _dev
    yield
    app.dependency_overrides.pop(get_current_developer, None)


@pytest.mark.asyncio
async def test_me_get_requires_auth(api_client) -> None:
    resp = await api_client.get("/api/v1/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_get_ok(api_client, _logged_in_alice) -> None:
    alice = _sample_developer()
    resp = await api_client.get("/api/v1/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["github_login"] == alice.github_login
    assert data["github_id"] == alice.github_id
    assert data["id"] == str(alice.id)
    assert data["island"] is None
    assert data["is_onboarded"] is False


@pytest.mark.asyncio
async def test_patch_me_requires_auth(api_client) -> None:
    resp = await api_client.patch("/api/v1/me", json={"island": "frontend"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_me_invalid_island_returns_422(api_client, _logged_in_alice) -> None:
    resp = await api_client.patch("/api/v1/me", json={"island": "not_a_real_island"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_updates_island(api_client, _logged_in_alice) -> None:
    updated = _sample_developer()
    updated.island = IslandChoice.FRONTEND.value

    class _Svc:
        async def update_profile(self, db, developer, payload):
            _ = (db, developer, payload)
            return updated

    app.dependency_overrides[get_developer_service] = lambda: _Svc()

    try:
        resp = await api_client.patch("/api/v1/me", json={"island": "frontend"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["island"] == "frontend"
    finally:
        app.dependency_overrides.pop(get_developer_service, None)


@pytest.mark.asyncio
async def test_patch_me_unknown_field_returns_422(api_client, _logged_in_alice) -> None:
    resp = await api_client.patch("/api/v1/me", json={"github_login": "hacker"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_onboarding_requires_auth(api_client) -> None:
    resp = await api_client.post("/api/v1/me/onboarding")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_onboarding_marks_developer_as_onboarded(api_client, _logged_in_alice) -> None:
    onboarded = _sample_developer()
    onboarded.island = IslandChoice.BACKEND.value
    onboarded.is_onboarded = True

    class _Svc:
        async def complete_onboarding(self, db, developer):
            _ = (db, developer)
            return onboarded

    app.dependency_overrides[get_developer_service] = lambda: _Svc()

    try:
        with patch("app.routers.me.update_planet_json") as mock_task:
            resp = await api_client.post("/api/v1/me/onboarding")
            assert resp.status_code == 200
            data = resp.json()
            assert data["is_onboarded"] is True
            assert data["island"] == "backend"
            mock_task.delay.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_developer_service, None)


@pytest.mark.asyncio
async def test_delete_me_requires_auth(api_client) -> None:
    resp = await api_client.delete("/api/v1/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_me_returns_204_and_clears_cookie(api_client, _logged_in_alice) -> None:
    class _Svc:
        async def delete_account(self, db, developer):
            _ = (db, developer)

    app.dependency_overrides[get_developer_service] = lambda: _Svc()

    try:
        resp = await api_client.delete("/api/v1/me")
        assert resp.status_code == 204
        set_cookie = resp.headers.get("set-cookie", "")
        assert "devplanet_session=" in set_cookie
        assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
    finally:
        app.dependency_overrides.pop(get_developer_service, None)


@pytest.mark.asyncio
async def test_delete_me_triggers_planet_update_when_onboarded(api_client) -> None:
    onboarded = _sample_developer()
    onboarded.is_onboarded = True
    onboarded.island = IslandChoice.BACKEND.value

    async def _dev() -> Developer:
        return onboarded

    app.dependency_overrides[get_current_developer] = _dev

    class _Svc:
        async def delete_account(self, db, developer):
            _ = (db, developer)

    app.dependency_overrides[get_developer_service] = lambda: _Svc()

    try:
        with patch("app.routers.me.update_planet_json") as mock_task:
            resp = await api_client.delete("/api/v1/me")
            assert resp.status_code == 204
            mock_task.delay.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_developer, None)
        app.dependency_overrides.pop(get_developer_service, None)


@pytest.mark.asyncio
async def test_delete_me_does_not_trigger_planet_update_when_not_onboarded(
    api_client, _logged_in_alice
) -> None:
    class _Svc:
        async def delete_account(self, db, developer):
            _ = (db, developer)

    app.dependency_overrides[get_developer_service] = lambda: _Svc()

    try:
        with patch("app.routers.me.update_planet_json") as mock_task:
            resp = await api_client.delete("/api/v1/me")
            assert resp.status_code == 204
            mock_task.delay.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_developer_service, None)
