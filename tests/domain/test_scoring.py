from datetime import UTC, datetime

import pytest
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.scoring import (
    _MAX_LEVEL,
    calculate_xp,
    get_cell_count,
    get_level,
    get_next_cell_unlock,
    get_player_class,
    get_xp_progress,
    stars_after_single_repo_cap,
    xp_for_level,
)


@pytest.mark.parametrize(
    ("stars", "expected_raw", "expected_capped_total"),
    [
        ([], 0, 0),
        ([42], 42, 42),
        ([30, 12], 42, 42),
        ([49], 49, 49),
        ([50], 50, 50),
        ([51], 51, 15),
        ([1000, 1, 1], 1002, 300 + 1 + 1),
        ([333, 333, 334], 1000, 300 + 300 + 300),
    ],
)
def test_star_cap_aggregate(
    stars: list[int],
    expected_raw: int,
    expected_capped_total: int,
) -> None:
    raw, capped_total = stars_after_single_repo_cap(tuple(stars))
    assert raw == expected_raw
    assert capped_total == expected_capped_total


def test_xp_minimum_inputs() -> None:
    inp = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        stars_per_repo=(),
        forks_received=0,
        followers=0,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    xp, breakdown = calculate_xp(inp)
    assert xp == 0
    assert breakdown.from_stars == 0


def test_first_player_class_matches_doc() -> None:
    klass = get_player_class(4)
    assert klass.name == "Seedling"
    assert klass.slug == "seedling"
    assert klass.tier == 1
    assert klass.required_level == 1


def test_player_class_advances_at_correct_level_boundaries() -> None:
    from app.domain.scoring import PLAYER_CLASSES_LIST

    for cls in PLAYER_CLASSES_LIST:
        resolved = get_player_class(cls.required_level)
        assert resolved.slug == cls.slug, f"Expected {cls.slug} at level {cls.required_level}"

    for i, cls in enumerate(PLAYER_CLASSES_LIST[1:], start=1):
        one_below = get_player_class(cls.required_level - 1)
        assert one_below.slug == PLAYER_CLASSES_LIST[i - 1].slug


def test_level_and_cells_zero_xp_anchor() -> None:
    xp = 0
    level = get_level(xp)
    assert level == 1
    assert get_cell_count(xp) == 1


def test_xp_progress_zero_is_level_one_percent_zero() -> None:
    prog = get_xp_progress(0)
    assert prog.level == 1
    assert prog.xp_in_level == 0
    assert prog.xp_needed == xp_for_level(2)
    assert prog.percent == 0


def test_level_follows_definition_of_cumulative_gateways() -> None:
    assert get_level(xp_for_level(10)) == 10
    assert get_level(max(0, xp_for_level(10) - 1)) == 9


def test_cell_count_increases_with_xp_under_regime_below_fifty_level() -> None:
    xp_low = 1_280
    xp_high = 1_281
    assert get_level(xp_low) <= 50
    assert get_cell_count(xp_high) >= get_cell_count(xp_low)


def test_next_cell_unlock_from_zero_xp() -> None:
    unlock = get_next_cell_unlock(0)
    assert unlock is not None
    assert unlock.in_current_level is True
    assert unlock.bar_percent is not None
    assert unlock.xp_in_level_at_unlock is not None
    assert unlock.xp_in_level_at_unlock == unlock.unlock_xp
    assert unlock.xp_remaining > 0


def test_next_cell_unlock_beyond_current_level() -> None:
    xp = xp_for_level(51)
    unlock = get_next_cell_unlock(xp)
    assert unlock is not None
    assert unlock.in_current_level is False
    assert unlock.bar_percent is None
    assert unlock.xp_in_level_at_unlock is None
    assert unlock.unlock_level == 52


def test_next_cell_unlock_none_at_max_cells() -> None:
    max_xp = xp_for_level(_MAX_LEVEL + 1) - 1
    assert get_next_cell_unlock(max_xp) is None


def test_private_contributions_xp_rate() -> None:
    inp = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=100,
        stars_per_repo=(),
        forks_received=0,
        followers=0,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_private_contributions == 1000
    assert xp == 1000


def test_repos_cap_for_xp_breakdown() -> None:
    inp = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        stars_per_repo=(0,) * 60,
        forks_received=0,
        followers=0,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_repos == 50 * 20
    assert xp == breakdown.from_repos


def test_followers_cap_for_xp_breakdown() -> None:
    inp = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        stars_per_repo=(),
        forks_received=0,
        followers=600,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_followers == 500 * 20
    assert xp == breakdown.from_followers
