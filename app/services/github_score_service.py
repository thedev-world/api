from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.datetime_github import github_account_age_full_years
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
    xp_breakdown_from_persisted_components,
)

if TYPE_CHECKING:
    from app.clients.github import GitHubStatsFetcher
    from app.models.developer import Developer


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
    # When set, overrides len(stars_per_repo) in public aggregates.count.
    owners_repos_count_override: int | None = None


def github_snapshot_from_inputs(
    login: str,
    github_inputs: GithubScoreInputs,
) -> GithubPublicScoreSnapshot:
    trimmed = login.strip()
    xp, breakdown = calculate_xp(github_inputs)
    xp_progress = get_xp_progress(xp)
    stars_raw, stars_capped = stars_after_single_repo_cap(github_inputs.stars_per_repo)

    return GithubPublicScoreSnapshot(
        login=trimmed,
        xp=xp,
        xp_breakdown=breakdown,
        xp_progress=xp_progress,
        cell_count=get_cell_count(xp),
        player_class=get_player_class(xp_progress.level),
        github_inputs=github_inputs,
        stars_raw_total=stars_raw,
        stars_capped_total=stars_capped,
        owners_repos_count_override=None,
    )


def github_snapshot_from_developer_row(login: str, dev: Developer) -> GithubPublicScoreSnapshot:
    trimmed = login.strip()
    years = github_account_age_full_years(dev.account_created_at)
    breakdown = xp_breakdown_from_persisted_components(
        commits_alltime=dev.commits_alltime,
        prs_contributions_alltime=dev.prs_contributions_alltime,
        reviews_alltime=dev.reviews_alltime,
        stars_received_capped=dev.stars_received_capped,
        forks_received=dev.forks_received,
        followers=dev.followers,
        years_on_github=years,
    )
    xp = dev.xp_brut
    xp_progress = get_xp_progress(xp)
    inp = GithubScoreInputs(
        commits_alltime=dev.commits_alltime,
        prs_contributions_alltime=dev.prs_contributions_alltime,
        reviews_alltime=dev.reviews_alltime,
        stars_per_repo=(),
        forks_received=dev.forks_received,
        followers=dev.followers,
        account_created_at=dev.account_created_at,
    )
    return GithubPublicScoreSnapshot(
        login=trimmed,
        xp=xp,
        xp_breakdown=breakdown,
        xp_progress=xp_progress,
        cell_count=get_cell_count(xp),
        player_class=get_player_class(xp_progress.level),
        github_inputs=inp,
        stars_raw_total=dev.stars_received_raw,
        stars_capped_total=dev.stars_received_capped,
        owners_repos_count_override=dev.owned_non_fork_repos_count,
    )


class GithubScoreService:
    def __init__(self, github: GitHubStatsFetcher) -> None:
        self._github = github

    async def build_public_snapshot(self, login: str) -> GithubPublicScoreSnapshot:
        fetch_login = login.strip()
        github_inputs = await self._github.fetch_score_inputs(fetch_login)
        return github_snapshot_from_inputs(fetch_login, github_inputs)
