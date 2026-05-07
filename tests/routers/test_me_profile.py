import uuid
from datetime import UTC, datetime

import pytest
from app.dependencies.auth import get_current_developer
from app.main import app
from app.models.developer import Developer


def _sample_developer() -> Developer:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return Developer(
        id=uuid.UUID("00000000-0000-4000-8000-000000000042"),
        github_id=42,
        github_login="alice",
        commits_alltime=1,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        forks_received=0,
        followers=0,
        stars_received_raw=3,
        stars_received_capped=3,
        owned_non_fork_repos_count=1,
        account_created_at=now,
        xp_brut=100,
        last_sync_at=now,
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
