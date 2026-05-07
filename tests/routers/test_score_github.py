from datetime import UTC, datetime

import pytest
from app.dependencies.providers import get_github_score_service
from app.domain.github_inputs import GitHubScoreInputs
from app.main import app
from app.services.github_score_service import GitHubScoreService


class _DummyFetcher:
    async def fetch_score_inputs(self, login: str) -> GitHubScoreInputs:
        _ = login
        return GitHubScoreInputs(
            commits_alltime=10,
            prs_contributions_alltime=1,
            reviews_alltime=1,
            stars_per_repo=(5,),
            forks_received=2,
            followers=10,
            account_created_at=datetime(2018, 6, 1, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_github_score_route_returns_payload(api_client) -> None:
    app.dependency_overrides[get_github_score_service] = lambda: GitHubScoreService(_DummyFetcher())

    resp = await api_client.get("/api/v1/github/alice/score")

    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "alice"
    assert "xp" in data
    assert data["xp_progress"]["level"] >= 1
    assert "breakdown" in data
    assert "commits" in data["breakdown"]
    assert "aggregates" in data
