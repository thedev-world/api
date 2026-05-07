from datetime import UTC, datetime

import pytest
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.scoring import (
    calculate_xp,
    get_cell_count,
    get_level,
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


def test_followers_cap_for_xp_breakdown() -> None:
    inp = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_per_repo=(),
        forks_received=0,
        followers=600,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    xp, breakdown = calculate_xp(inp)
    assert breakdown.from_followers == 500 * 20
    assert xp == breakdown.from_followers
