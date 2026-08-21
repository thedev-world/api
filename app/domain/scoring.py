from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.datetime_github import github_account_age_full_years
from app.domain.github_inputs import GitHubScoreInputs

FOLLOWERS_COUNT_CAP_FOR_XP = 500
OWNED_REPOS_COUNT_CAP_FOR_XP = 50
XP_PER_OWNED_REPO = 20
STARS_SUM_SKIP_PER_REPO_CAP = 50
COMMITS_FARM_MIN_COMMITS = 15_000
COMMITS_FARM_RATIO_THRESHOLD = 4.0
XP_PER_PRIVATE_CONTRIBUTION = 10


@dataclass(frozen=True, slots=True)
class XpBreakdownContribution:
    from_commits: int
    from_pull_requests: int
    from_reviews: int
    from_private_contributions: int
    from_stars: int
    from_forks: int
    from_followers: int
    from_repos: int
    from_tenure: int


@dataclass(frozen=True, slots=True)
class XpProgress:
    level: int
    xp_in_level: int
    xp_needed: int
    percent: int


@dataclass(frozen=True, slots=True)
class PlayerClass:
    slug: str
    name: str
    tier: int
    required_level: int
    phrase: str


def stars_after_single_repo_cap(stars_per_repo: tuple[int, ...]) -> tuple[int, int]:
    total_raw = sum(stars_per_repo)
    if total_raw <= 0:
        return (0, 0)
    if total_raw <= STARS_SUM_SKIP_PER_REPO_CAP:
        return (total_raw, total_raw)
    cap = math.floor(0.3 * total_raw)
    capped_total = sum(min(s, cap) for s in stars_per_repo)
    return (total_raw, capped_total)


def evaluate_commits_farm_flag(commits_alltime: int, breakdown_sum: int) -> bool:
    if commits_alltime <= COMMITS_FARM_MIN_COMMITS:
        return False
    if breakdown_sum <= 0:
        return False
    return commits_alltime / breakdown_sum > COMMITS_FARM_RATIO_THRESHOLD


def commits_for_xp(
    commits_alltime: int,
    breakdown_sum: int,
    farm_flagged: bool,
    farm_cleared: bool,
) -> int:
    if farm_flagged and not farm_cleared:
        return breakdown_sum
    return commits_alltime


def owned_repos_for_xp(count: int) -> int:
    return min(max(0, count), OWNED_REPOS_COUNT_CAP_FOR_XP)


def xp_breakdown_from_persisted_components(
    *,
    commits_alltime: int,
    prs_contributions_alltime: int,
    reviews_alltime: int,
    private_contributions_alltime: int,
    stars_received_capped: int,
    forks_received: int,
    followers: int,
    owned_non_fork_repos_count: int,
    years_on_github: int,
) -> XpBreakdownContribution:
    """XP slice from stored scalars (stars cap already applied upstream)."""
    b_commits = commits_alltime * 10
    b_prs = prs_contributions_alltime * 30
    b_reviews = reviews_alltime * 15
    b_private = private_contributions_alltime * 10
    b_stars = stars_received_capped * 50
    b_forks = forks_received * 40
    followers_for_xp = min(followers, FOLLOWERS_COUNT_CAP_FOR_XP)
    b_follow = followers_for_xp * 20
    repos_for_xp = owned_repos_for_xp(owned_non_fork_repos_count)
    b_repos = repos_for_xp * XP_PER_OWNED_REPO
    b_years = years_on_github * 200

    return XpBreakdownContribution(
        from_commits=b_commits,
        from_pull_requests=b_prs,
        from_reviews=b_reviews,
        from_private_contributions=b_private,
        from_stars=b_stars,
        from_forks=b_forks,
        from_followers=b_follow,
        from_repos=b_repos,
        from_tenure=b_years,
    )


def calculate_xp(inputs: GitHubScoreInputs) -> tuple[int, XpBreakdownContribution]:
    _, stars_capped = stars_after_single_repo_cap(inputs.stars_per_repo)

    years = github_account_age_full_years(inputs.account_created_at)
    effective_commits = commits_for_xp(
        inputs.commits_alltime,
        inputs.commits_breakdown_sum,
        inputs.commits_farm_flagged,
        inputs.commits_farm_cleared,
    )
    breakdown = xp_breakdown_from_persisted_components(
        commits_alltime=effective_commits,
        prs_contributions_alltime=inputs.prs_contributions_alltime,
        reviews_alltime=inputs.reviews_alltime,
        private_contributions_alltime=inputs.private_contributions_alltime,
        stars_received_capped=stars_capped,
        forks_received=inputs.forks_received,
        followers=inputs.followers,
        owned_non_fork_repos_count=len(inputs.stars_per_repo),
        years_on_github=years,
    )

    xp = (
        breakdown.from_commits
        + breakdown.from_pull_requests
        + breakdown.from_reviews
        + breakdown.from_private_contributions
        + breakdown.from_stars
        + breakdown.from_forks
        + breakdown.from_followers
        + breakdown.from_repos
        + breakdown.from_tenure
    )
    return xp, breakdown


def xp_for_level(level: int) -> int:
    if level < 1:
        raise ValueError("level must be >= 1")
    return round(100 * math.pow(level, 1.8))


_MAX_LEVEL = 200
# 200 levels gives ample headroom beyond the current Founder tier (lvl ~100).
# TODO: profile real whale users to determine whether a hard cap in business logic
#       (get_level, get_xp_progress) is actually needed, or if 200 stays as a safe ceiling.


def _build_level_thresholds() -> tuple[int, ...]:
    """XP required to reach each level, indexed from 1.
    thresholds[0] = 0     (level 1 starts at 0 XP — matches get_xp_progress floor)
    thresholds[1] = 348   (level 2 requires 348 XP)
    thresholds[i] = xp_for_level(i + 1)
    """
    return tuple(0 if level == 1 else xp_for_level(level) for level in range(1, _MAX_LEVEL + 1))


# Computed once at module import, lives in RAM for the lifetime of the process.
LEVEL_XP_THRESHOLDS: tuple[int, ...] = _build_level_thresholds()


def get_level(xp: int) -> int:
    if xp < 0:
        raise ValueError("xp cannot be negative")
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def get_xp_progress(xp: int) -> XpProgress:
    level = get_level(xp)
    # Level 1 spans [0, xp_for_level(2)); xp_for_level(1) is not a gameplay floor for get_level().
    xp_floor = 0 if level == 1 else xp_for_level(level)
    xp_next_level = xp_for_level(level + 1)
    span = xp_next_level - xp_floor
    xp_in_level = xp - xp_floor
    if span <= 0:
        pct = 100
    else:
        pct = max(0, min(100, round(xp_in_level / span * 100)))
    return XpProgress(
        level=level,
        xp_in_level=xp_in_level,
        xp_needed=span,
        percent=pct,
    )


_BASE_AT_LEVEL_50 = 1 + round(math.pow(115_000 / 100, 0.62))


def get_cell_count(xp: int) -> int:
    if xp < 0:
        raise ValueError("xp cannot be negative")
    level = get_level(xp)
    if level <= 50:
        return 1 + round(math.pow(xp / 100, 0.62))
    whale_bonus = round(math.pow(level - 50, 1.2) * 2)
    return _BASE_AT_LEVEL_50 + whale_bonus


PLAYER_CLASSES_LIST: tuple[PlayerClass, ...] = (
    PlayerClass(
        slug="seedling",
        name="Seedling",
        tier=1,
        required_level=1,
        phrase="It compiles. That's something.",
    ),
    PlayerClass(
        slug="builder",
        name="Builder",
        tier=2,
        required_level=5,
        phrase="You build, it breaks, you rebuild.",
    ),
    PlayerClass(
        slug="crafter",
        name="Crafter",
        tier=3,
        required_level=10,
        phrase="People read your code without crying.",
    ),
    PlayerClass(
        slug="architect",
        name="Architect",
        tier=4,
        required_level=20,
        phrase="You open issues on repos you didn't write.",
    ),
    PlayerClass(
        slug="maintainer",
        name="Maintainer",
        tier=5,
        required_level=35,
        phrase="You merge PRs on Sundays. On purpose.",
    ),
    PlayerClass(
        slug="legend",
        name="Legend",
        tier=6,
        required_level=55,
        phrase="People learned to code on your code.",
    ),
    PlayerClass(
        slug="sovereign",
        name="Sovereign",
        tier=7,
        required_level=80,
        phrase="You deprecate APIs. People adapt.",
    ),
    PlayerClass(
        slug="founder",
        name="Founder",
        tier=8,
        required_level=100,
        phrase="Someone forked your thing. Good. That was the point.",
    ),
)


def get_player_class(level: int) -> PlayerClass:
    current = PLAYER_CLASSES_LIST[0]
    for cls in PLAYER_CLASSES_LIST:
        if level >= cls.required_level:
            current = cls
    return current
