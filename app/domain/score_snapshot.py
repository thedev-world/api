"""Domain objects representing a computed score snapshot and sync progress.

These are pure data containers with no I/O or HTTP concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.datetime_github import github_account_age_full_years
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.scoring import (
    PlayerClass,
    XpBreakdownContribution,
    XpProgress,
    calculate_xp,
    commits_for_xp,
    get_cell_count,
    get_player_class,
    get_xp_progress,
    stars_after_single_repo_cap,
    xp_breakdown_from_persisted_components,
)

if TYPE_CHECKING:
    from app.models.developer import Developer


@dataclass(frozen=True, slots=True)
class GitHubPublicScoreSnapshot:
    login: str
    xp: int
    xp_breakdown: XpBreakdownContribution
    xp_progress: XpProgress
    cell_count: int
    player_class: PlayerClass
    github_inputs: GitHubScoreInputs
    stars_raw_total: int
    stars_capped_total: int
    # When set, overrides len(stars_per_repo) in public aggregates count.
    owners_repos_count_override: int | None = None


@dataclass(frozen=True, slots=True)
class SyncProgress:
    """Delta between the previous and new snapshot after a sync."""

    xp_before: int
    xp_after: int
    level_before: int
    level_after: int
    cell_before: int
    cell_after: int
    xp_progress_before: XpProgress
    xp_progress_after: XpProgress
    breakdown_before: XpBreakdownContribution
    breakdown_after: XpBreakdownContribution


def github_snapshot_from_inputs(
    login: str,
    github_inputs: GitHubScoreInputs,
) -> GitHubPublicScoreSnapshot:
    trimmed = login.strip()
    xp, breakdown = calculate_xp(github_inputs)
    xp_progress = get_xp_progress(xp)
    stars_raw, stars_capped = stars_after_single_repo_cap(github_inputs.stars_per_repo)

    return GitHubPublicScoreSnapshot(
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


def github_snapshot_from_developer_row(login: str, dev: Developer) -> GitHubPublicScoreSnapshot:
    trimmed = login.strip()
    years = github_account_age_full_years(dev.account_created_at)
    effective_commits = commits_for_xp(
        dev.commits_alltime,
        dev.commits_breakdown_sum,
        dev.commits_farm_flagged,
        dev.commits_farm_cleared,
    )
    breakdown = xp_breakdown_from_persisted_components(
        commits_alltime=effective_commits,
        prs_contributions_alltime=dev.prs_contributions_alltime,
        reviews_alltime=dev.reviews_alltime,
        private_contributions_alltime=dev.private_contributions_alltime,
        stars_received_capped=dev.stars_received_capped,
        forks_received=dev.forks_received,
        followers=dev.followers,
        owned_non_fork_repos_count=dev.owned_non_fork_repos_count,
        years_on_github=years,
    )
    xp = dev.xp_brut
    xp_progress = get_xp_progress(xp)
    inp = GitHubScoreInputs(
        commits_alltime=dev.commits_alltime,
        prs_contributions_alltime=dev.prs_contributions_alltime,
        reviews_alltime=dev.reviews_alltime,
        private_contributions_alltime=dev.private_contributions_alltime,
        stars_per_repo=(),
        forks_received=dev.forks_received,
        followers=dev.followers,
        account_created_at=dev.account_created_at,
        commits_breakdown_sum=dev.commits_breakdown_sum,
        commits_farm_flagged=dev.commits_farm_flagged,
        commits_farm_cleared=dev.commits_farm_cleared,
    )
    return GitHubPublicScoreSnapshot(
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
