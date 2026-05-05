from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.github_inputs import GithubScoreInputs

FOLLOWERS_COUNT_CAP_FOR_XP = 500
STARS_SUM_SKIP_PER_REPO_CAP = 50


@dataclass(frozen=True, slots=True)
class XpBreakdownContribution:
    from_commits: int
    from_pull_requests: int
    from_reviews: int
    from_stars: int
    from_forks: int
    from_followers: int
    from_tenure: int


@dataclass(frozen=True, slots=True)
class XpProgress:
    level: int
    xp_in_level: int
    xp_needed: int
    percent: int


@dataclass(frozen=True, slots=True)
class PlayerClass:
    name: str
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


def calculate_xp(inputs: GithubScoreInputs) -> tuple[int, XpBreakdownContribution]:
    _, stars_capped = stars_after_single_repo_cap(inputs.stars_per_repo)

    b_commits = inputs.commits_alltime * 10
    b_prs = inputs.prs_contributions_alltime * 30
    b_reviews = inputs.reviews_alltime * 15
    b_stars = stars_capped * 50
    b_forks = inputs.forks_received * 40
    followers_for_xp = min(inputs.followers, FOLLOWERS_COUNT_CAP_FOR_XP)
    b_follow = followers_for_xp * 20
    b_years = inputs.years_on_github * 200

    xp = b_commits + b_prs + b_reviews + b_stars + b_forks + b_follow + b_years
    breakdown = XpBreakdownContribution(
        from_commits=b_commits,
        from_pull_requests=b_prs,
        from_reviews=b_reviews,
        from_stars=b_stars,
        from_forks=b_forks,
        from_followers=b_follow,
        from_tenure=b_years,
    )
    return xp, breakdown


def xp_for_level(level: int) -> int:
    if level < 1:
        raise ValueError("level must be >= 1")
    return round(100 * math.pow(level, 1.8))


def get_level(xp: int) -> int:
    if xp < 0:
        raise ValueError("xp cannot be negative")
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def get_xp_progress(xp: int) -> XpProgress:
    level = get_level(xp)
    xp_current_level = xp_for_level(level)
    xp_next_level = xp_for_level(level + 1)
    span = xp_next_level - xp_current_level
    xp_in_level = xp - xp_current_level
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


def get_player_class(level: int) -> PlayerClass:
    classes: list[tuple[int, str, str]] = [
        (1, "Seedling", "Tu plantes les premières graines."),
        (5, "Builder", "Tu construis, commit après commit."),
        (10, "Crafter", "Ton travail commence à résonner."),
        (20, "Architect", "Tu shapes des projets entiers."),
        (35, "Maintainer", "La communauté compte sur toi."),
        (55, "Legend", "Ton impact dépasse ton île."),
        (80, "Sovereign", "Tu gouvernes ton territoire."),
        (100, "Founder", "Tu as posé les fondations du monde."),
    ]
    current = classes[0]
    for min_level, name, phrase in classes:
        if level >= min_level:
            current = (min_level, name, phrase)
    return PlayerClass(name=current[1], phrase=current[2])
