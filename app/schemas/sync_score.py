from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.score import GithubPublicScoreResponse, XpProgressSchema


class MeSyncRequestBody(BaseModel):
    """Open testing phase: caller passes which GitHub user to sync."""

    model_config = ConfigDict(extra="forbid")

    github_login: str = Field(
        ...,
        min_length=1,
        description=(
            "GitHub login to persist. With OAuth later, this will come from the access token "
            "and body may be ignored."
        ),
    )


class ScoreXpBreakdownDeltaSchema(BaseModel):
    """XP-point deltas inside each breakdown bucket."""

    model_config = ConfigDict(extra="forbid")

    commits: int
    pull_requests: int
    reviews: int
    stars: int
    forks: int
    followers: int
    tenure_years_bonus: int


class ScoreSyncProgressSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xp_before: int
    xp_after: int
    level_before: int
    level_after: int
    cell_before: int
    cell_after: int
    xp_progress_before: XpProgressSchema
    xp_progress_after: XpProgressSchema
    breakdown_delta: ScoreXpBreakdownDeltaSchema


class MeSyncCooldownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sync_performed: Literal[False] = False
    cooldown_active: Literal[True] = True
    retry_after: datetime


class MeSyncPerformedResponse(GithubPublicScoreResponse):
    model_config = ConfigDict(extra="forbid")

    sync_performed: Literal[True] = True
    first_sync: bool
    progress: ScoreSyncProgressSchema | None = None


MeSyncUnionResponse = Annotated[
    MeSyncCooldownResponse | MeSyncPerformedResponse,
    Field(discriminator="sync_performed"),
]
