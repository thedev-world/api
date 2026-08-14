from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.island import IslandChoice
from app.domain.scoring import get_cell_count, get_player_class, get_xp_progress
from app.models.developer import Developer
from app.schemas.score import PlayerClassSchema, XpProgressSchema
from app.services.score_sync_service import SYNC_COOLDOWN


class DeveloperPublicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    github_id: int
    github_login: str
    commits_alltime: int
    prs_contributions_alltime: int
    reviews_alltime: int
    private_contributions_alltime: int
    forks_received: int
    followers: int
    stars_received_raw: int
    stars_received_capped: int
    owned_non_fork_repos_count: int
    account_created_at: datetime
    xp_brut: int
    xp_progress: XpProgressSchema
    cell_count: int
    player_class: PlayerClassSchema
    last_sync_at: datetime | None
    next_sync_at: datetime | None
    island: IslandChoice | None
    is_onboarded: bool
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime


def developer_public_from_orm(row: Developer) -> DeveloperPublicResponse:
    prog = get_xp_progress(row.xp_brut)
    klass = get_player_class(prog.level)
    return DeveloperPublicResponse(
        id=row.id,
        github_id=row.github_id,
        github_login=row.github_login,
        commits_alltime=row.commits_alltime,
        prs_contributions_alltime=row.prs_contributions_alltime,
        reviews_alltime=row.reviews_alltime,
        private_contributions_alltime=row.private_contributions_alltime,
        forks_received=row.forks_received,
        followers=row.followers,
        stars_received_raw=row.stars_received_raw,
        stars_received_capped=row.stars_received_capped,
        owned_non_fork_repos_count=row.owned_non_fork_repos_count,
        account_created_at=row.account_created_at,
        xp_brut=row.xp_brut,
        xp_progress=XpProgressSchema(
            level=prog.level,
            xp_in_level=prog.xp_in_level,
            xp_needed=prog.xp_needed,
            percent=prog.percent,
        ),
        cell_count=get_cell_count(row.xp_brut),
        player_class=PlayerClassSchema(name=klass.name, phrase=klass.phrase),
        last_sync_at=row.last_sync_at,
        next_sync_at=row.last_sync_at + SYNC_COOLDOWN if row.last_sync_at else None,
        island=IslandChoice(row.island) if row.island else None,
        is_onboarded=row.is_onboarded,
        avatar_url=row.avatar_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
