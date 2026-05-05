from dataclasses import dataclass

from app.clients.github import GitHubStatsFetcher
from app.domain.github_inputs import GithubScoreInputs
from app.domain.scoring import (
    PlayerClass,
    XpBreakdownContribution,
    XpProgress,
    calculate_xp,
    get_cell_count,
    get_player_class,
    get_xp_progress,
    stars_after_single_repo_cap,
)


@dataclass(frozen=True, slots=True)
class GithubPublicScoreSnapshot:
    login: str
    xp: int
    xp_breakdown: XpBreakdownContribution
    xp_progress: XpProgress
    cell_count: int
    player_class: PlayerClass
    github_inputs: GithubScoreInputs
    stars_raw_total: int
    stars_capped_total: int


class GithubScoreService:
    def __init__(self, github: GitHubStatsFetcher) -> None:
        self._github = github

    async def build_public_snapshot(self, login: str) -> GithubPublicScoreSnapshot:
        fetch_login = login.strip()
        github_inputs = await self._github.fetch_score_inputs(fetch_login)

        xp, breakdown = calculate_xp(github_inputs)
        xp_progress = get_xp_progress(xp)
        cell_count = get_cell_count(xp)
        stars_raw, stars_capped = stars_after_single_repo_cap(github_inputs.stars_per_repo)

        return GithubPublicScoreSnapshot(
            login=fetch_login,
            xp=xp,
            xp_breakdown=breakdown,
            xp_progress=xp_progress,
            cell_count=cell_count,
            player_class=get_player_class(xp_progress.level),
            github_inputs=github_inputs,
            stars_raw_total=stars_raw,
            stars_capped_total=stars_capped,
        )
