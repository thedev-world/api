from datetime import UTC, datetime

import pytest
from app.domain.github_inputs import GithubScoreInputs
from app.domain.scoring import stars_after_single_repo_cap
from app.services.github_score_service import GithubScoreService


class StubGitHubFetcher:
    def __init__(self, payload: GithubScoreInputs) -> None:
        self._payload = payload

    async def fetch_score_inputs(self, login: str) -> GithubScoreInputs:
        _ = login
        return self._payload


@pytest.mark.asyncio
async def test_service_build_snapshot_reflects_github_inputs() -> None:
    inp = GithubScoreInputs(
        commits_alltime=1,
        prs_contributions_alltime=1,
        reviews_alltime=1,
        stars_per_repo=(10,),
        forks_received=2,
        followers=3,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    service = GithubScoreService(StubGitHubFetcher(inp))
    snap = await service.build_public_snapshot("any")

    raw, capped_total = stars_after_single_repo_cap(inp.stars_per_repo)

    assert snap.login == "any"
    assert snap.cell_count >= 1
    assert snap.stars_raw_total == raw
    assert snap.stars_capped_total == capped_total
    assert snap.player_class.name
    assert snap.xp_progress.level >= 1
