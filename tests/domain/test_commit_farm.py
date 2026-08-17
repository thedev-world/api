"""Commit-farm detection and XP cap on visible breakdown."""

from datetime import UTC, datetime

from app.domain.github_inputs import GitHubScoreInputs
from app.domain.scoring import (
    COMMITS_FARM_MIN_COMMITS,
    calculate_xp,
    commits_for_xp,
    evaluate_commits_farm_flag,
)


def _inputs(
    *,
    commits_alltime: int,
    breakdown_sum: int = 0,
    farm_flagged: bool = False,
    farm_cleared: bool = False,
) -> GitHubScoreInputs:
    return GitHubScoreInputs(
        commits_alltime=commits_alltime,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        stars_per_repo=(),
        forks_received=0,
        followers=0,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
        commits_breakdown_sum=breakdown_sum,
        commits_farm_flagged=farm_flagged,
        commits_farm_cleared=farm_cleared,
    )


def test_evaluate_commits_farm_flag_flolep_like() -> None:
    assert evaluate_commits_farm_flag(26792, 800) is True


def test_evaluate_commits_farm_flag_maxime_like() -> None:
    assert evaluate_commits_farm_flag(2491, 1491) is False


def test_evaluate_commits_farm_flag_below_min_commits() -> None:
    assert evaluate_commits_farm_flag(COMMITS_FARM_MIN_COMMITS, 1) is False


def test_evaluate_commits_farm_flag_zero_breakdown() -> None:
    assert evaluate_commits_farm_flag(COMMITS_FARM_MIN_COMMITS + 1, 0) is False


def test_evaluate_commits_farm_flag_at_ratio_threshold() -> None:
    assert evaluate_commits_farm_flag(20_000, 5_000) is False


def test_evaluate_commits_farm_flag_just_above_ratio_threshold() -> None:
    assert evaluate_commits_farm_flag(20_001, 5_000) is True


def test_commits_for_xp_uses_breakdown_when_flagged() -> None:
    assert commits_for_xp(26792, 800, farm_flagged=True, farm_cleared=False) == 800


def test_commits_for_xp_uses_alltime_when_not_flagged() -> None:
    assert commits_for_xp(2491, 1491, farm_flagged=False, farm_cleared=False) == 2491


def test_commits_for_xp_uses_alltime_when_cleared() -> None:
    assert commits_for_xp(26792, 800, farm_flagged=True, farm_cleared=True) == 26792


def test_calculate_xp_flolep_like_scores_breakdown_only() -> None:
    inp = _inputs(commits_alltime=26792, breakdown_sum=800, farm_flagged=True)
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_commits == 800 * 10
    assert xp == breakdown.from_commits


def test_calculate_xp_maxime_like_scores_alltime() -> None:
    inp = _inputs(commits_alltime=2491, breakdown_sum=1491, farm_flagged=False)
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_commits == 2491 * 10
    assert xp == breakdown.from_commits
