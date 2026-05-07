from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.clients.github import GitHubAPIError
from app.dependencies.auth import get_current_developer
from app.dependencies.providers import get_score_sync_service
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.score_snapshot import SyncProgress, github_snapshot_from_inputs
from app.domain.scoring import get_xp_progress
from app.main import app
from app.models.developer import Developer
from app.schemas.score import public_score_response_from
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed

_FUTURE_ACCOUNT = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture
def _logged_in_alice() -> None:
    async def _dev() -> Developer:
        m = MagicMock(spec=Developer)
        m.github_id = 42
        m.github_login = "alice"
        return m

    app.dependency_overrides[get_current_developer] = _dev
    yield
    app.dependency_overrides.pop(get_current_developer, None)


@pytest.mark.asyncio
async def test_me_sync_requires_auth(api_client) -> None:
    resp = await api_client.post("/api/v1/me/sync")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_sync_cooldown_body(api_client, _logged_in_alice) -> None:
    retry = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    class _CoolService:
        async def sync_for_actor(self, db, *, github_id: int, login: str) -> MeSyncCooldown:
            _ = (db, github_id, login)
            return MeSyncCooldown(retry_after=retry)

    app.dependency_overrides[get_score_sync_service] = _CoolService

    resp = await api_client.post("/api/v1/me/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_performed"] is False
    assert data["cooldown_active"] is True
    assert "retry_after" in data


@pytest.mark.asyncio
async def test_me_sync_performed_json_shape(api_client, _logged_in_alice) -> None:
    inp = GitHubScoreInputs(
        commits_alltime=1,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_per_repo=(5,),
        forks_received=0,
        followers=0,
        account_created_at=_FUTURE_ACCOUNT,
    )
    snap = github_snapshot_from_inputs("alice", inp)
    zero_snap = github_snapshot_from_inputs(
        "alice",
        GitHubScoreInputs(
            commits_alltime=0,
            prs_contributions_alltime=0,
            reviews_alltime=0,
            stars_per_repo=(),
            forks_received=0,
            followers=0,
            account_created_at=_FUTURE_ACCOUNT,
        ),
    )
    progress = SyncProgress(
        xp_before=0,
        xp_after=snap.xp,
        level_before=1,
        level_after=snap.xp_progress.level,
        cell_before=snap.cell_count,
        cell_after=snap.cell_count,
        xp_progress_before=get_xp_progress(0),
        xp_progress_after=snap.xp_progress,
        breakdown_before=zero_snap.xp_breakdown,
        breakdown_after=snap.xp_breakdown,
    )

    class _OkService:
        async def sync_for_actor(self, db, *, github_id: int, login: str) -> MeSyncPerformed:
            _ = (db, github_id, login)
            return MeSyncPerformed(first_sync=False, snapshot=snap, progress=progress)

    app.dependency_overrides[get_score_sync_service] = _OkService

    resp = await api_client.post("/api/v1/me/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_performed"] is True
    assert data["first_sync"] is False
    assert "commits" in data["breakdown"]
    assert data["progress"]["xp_after"] == snap.xp
    assert data["progress"]["cell_before"] == snap.cell_count
    assert data["progress"]["cell_after"] == snap.cell_count
    payload = public_score_response_from(snap)
    assert data["progress"]["xp_progress_before"]["percent"] == get_xp_progress(0).percent
    assert data["progress"]["xp_progress_after"] == payload.xp_progress.model_dump(by_alias=False)


@pytest.mark.asyncio
async def test_me_sync_503_propagates_github_api_message(api_client, _logged_in_alice) -> None:
    class _ErrService:
        async def sync_for_actor(self, db, *, github_id: int, login: str) -> None:
            _ = (db, github_id, login)
            raise GitHubAPIError('GraphQL HTTP 401: {"message":"Bad credentials"}')

    app.dependency_overrides[get_score_sync_service] = _ErrService

    try:
        resp = await api_client.post("/api/v1/me/sync")
        assert resp.status_code == 503
        assert "Bad credentials" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_score_sync_service, None)
