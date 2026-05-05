from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.datetime_github import github_account_age_full_years
from app.services.github_score_service import GithubPublicScoreSnapshot


class ScoreXpBreakdownSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_commits: int = Field(serialization_alias="commits")
    from_pull_requests: int = Field(serialization_alias="pull_requests")
    from_reviews: int = Field(serialization_alias="reviews")
    from_stars: int = Field(serialization_alias="stars")
    from_forks: int = Field(serialization_alias="forks")
    from_followers: int = Field(serialization_alias="followers")
    from_tenure: int = Field(serialization_alias="tenure_years_bonus")


class XpProgressSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int
    xp_in_level: int
    xp_needed: int
    percent: int


class PlayerClassSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    phrase: str


class GithubAggregatesPublicSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commits_alltime: int
    prs_contributions_alltime: int = Field(
        ...,
        description="GitHub totalPullRequestContributions (opened PRs; merges not guaranteed).",
    )
    reviews_alltime: int
    forks_received_on_owned_repos: int
    followers: int
    years_on_github: int
    owners_repos_count_non_fork: int
    stars_received_raw_total: int
    stars_received_capped_total: int


class GithubPublicScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str
    xp: int
    breakdown: ScoreXpBreakdownSchema
    xp_progress: XpProgressSchema
    cell_count: int
    player_class: PlayerClassSchema
    aggregates: GithubAggregatesPublicSchema


def public_score_response_from(snapshot: GithubPublicScoreSnapshot) -> GithubPublicScoreResponse:
    inp = snapshot.github_inputs
    b = snapshot.xp_breakdown
    p = snapshot.xp_progress
    cls = snapshot.player_class
    repo_count = (
        snapshot.owners_repos_count_override
        if snapshot.owners_repos_count_override is not None
        else len(inp.stars_per_repo)
    )
    return GithubPublicScoreResponse(
        login=snapshot.login,
        xp=snapshot.xp,
        breakdown=ScoreXpBreakdownSchema(
            from_commits=b.from_commits,
            from_pull_requests=b.from_pull_requests,
            from_reviews=b.from_reviews,
            from_stars=b.from_stars,
            from_forks=b.from_forks,
            from_followers=b.from_followers,
            from_tenure=b.from_tenure,
        ),
        xp_progress=XpProgressSchema(
            level=p.level,
            xp_in_level=p.xp_in_level,
            xp_needed=p.xp_needed,
            percent=p.percent,
        ),
        cell_count=snapshot.cell_count,
        player_class=PlayerClassSchema(name=cls.name, phrase=cls.phrase),
        aggregates=GithubAggregatesPublicSchema(
            commits_alltime=inp.commits_alltime,
            prs_contributions_alltime=inp.prs_contributions_alltime,
            reviews_alltime=inp.reviews_alltime,
            forks_received_on_owned_repos=inp.forks_received,
            followers=inp.followers,
            years_on_github=github_account_age_full_years(inp.account_created_at),
            owners_repos_count_non_fork=repo_count,
            stars_received_raw_total=snapshot.stars_raw_total,
            stars_received_capped_total=snapshot.stars_capped_total,
        ),
    )
