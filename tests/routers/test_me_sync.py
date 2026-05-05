from datetime import UTC, datetime

import pytest
from app.clients.github import GitHubAPIError
from app.domain.github_inputs import GithubScoreInputs
from app.domain.scoring import get_xp_progress
from app.main import app
from app.routers.me import get_score_sync_service
from app.schemas.score import XpProgressSchema, public_score_response_from
from app.schemas.sync_score import ScoreSyncProgressSchema, ScoreXpBreakdownDeltaSchema
from app.services.github_score_service import github_snapshot_from_inputs
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed

_FUTURE_ACCOUNT = datetime(2030, 1, 1, tzinfo=UTC)


def _xp_progress_schema_from_domain(progress: object) -> XpProgressSchema:
    return XpProgressSchema(
        level=progress.level,
        xp_in_level=progress.xp_in_level,
        xp_needed=progress.xp_needed,
        percent=progress.percent,
    )


@pytest.mark.asyncio
async def test_me_sync_cooldown_body(api_client) -> None:
    retry = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    class _CoolService:
        async def sync_for_github_login(self, db, *, github_login: str) -> MeSyncCooldown:
            _ = (db, github_login)
            return MeSyncCooldown(retry_after=retry)

    app.dependency_overrides[get_score_sync_service] = _CoolService

    resp = await api_client.post(
        "/api/v1/me/sync",
        json={"github_login": "alice"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_performed"] is False
    assert data["cooldown_active"] is True
    assert "retry_after" in data


@pytest.mark.asyncio
async def test_me_sync_performed_json_shape(api_client) -> None:
    inp = GithubScoreInputs(
        commits_alltime=1,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_per_repo=(5,),
        forks_received=0,
        followers=0,
        account_created_at=_FUTURE_ACCOUNT,
    )
    snap = github_snapshot_from_inputs("alice", inp)
    payload = public_score_response_from(snap)
    progress = ScoreSyncProgressSchema(
        xp_before=0,
        xp_after=snap.xp,
        level_before=1,
        level_after=snap.xp_progress.level,
        cell_before=snap.cell_count,
        cell_after=snap.cell_count,
        xp_progress_before=_xp_progress_schema_from_domain(get_xp_progress(0)),
        xp_progress_after=_xp_progress_schema_from_domain(snap.xp_progress),
        breakdown_delta=ScoreXpBreakdownDeltaSchema(
            commits=snap.xp_breakdown.from_commits,
            pull_requests=0,
            reviews=0,
            stars=0,
            forks=0,
            followers=0,
            tenure_years_bonus=0,
        ),
    )

    class _OkService:
        async def sync_for_github_login(self, db, *, github_login: str) -> MeSyncPerformed:
            _ = (db, github_login)
            return MeSyncPerformed(first_sync=False, payload=payload, progress=progress)

    app.dependency_overrides[get_score_sync_service] = _OkService

    resp = await api_client.post(
        "/api/v1/me/sync",
        json={"github_login": "alice"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_performed"] is True
    assert data["first_sync"] is False
    assert "commits" in data["breakdown"]
    assert data["progress"]["xp_after"] == snap.xp
    assert data["progress"]["cell_before"] == snap.cell_count
    assert data["progress"]["cell_after"] == snap.cell_count
    assert data["progress"]["xp_progress_before"]["percent"] == get_xp_progress(0).percent
    assert data["progress"]["xp_progress_after"] == payload.xp_progress.model_dump(by_alias=False)


@pytest.mark.asyncio
async def test_me_sync_503_propagates_github_api_message(api_client) -> None:
    class _ErrService:
        async def sync_for_github_login(self, db, *, github_login: str) -> None:
            _ = (db, github_login)
            raise GitHubAPIError('GraphQL HTTP 401: {"message":"Bad credentials"}')

    app.dependency_overrides[get_score_sync_service] = _ErrService

    try:
        resp = await api_client.post(
            "/api/v1/me/sync",
            json={"github_login": "alice"},
        )
        assert resp.status_code == 503
        assert "Bad credentials" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_score_sync_service, None)
