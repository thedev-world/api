from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.github_oauth_scopes import has_github_org_oauth_scope
from app.domain.island import IslandChoice
from app.domain.scoring import (
    get_cell_count,
    get_next_cell_unlock,
    get_player_class,
    get_xp_progress,
)
from app.models.developer import Developer
from app.schemas.score import NextCellUnlockSchema, PlayerClassSchema, XpProgressSchema
from app.services.score_sync_service import SYNC_COOLDOWN


class DeveloperPublicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    github_id: int
    github_login: str
    commits_alltime: int
    commits_breakdown_sum: int
    commits_farm_flagged: bool
    commits_farm_cleared: bool
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
    next_cell_unlock: NextCellUnlockSchema | None
    player_class: PlayerClassSchema
    last_sync_at: datetime | None
    next_sync_at: datetime | None
    island: IslandChoice | None
    is_onboarded: bool
    avatar_url: str | None
    github_org_access_enabled: bool
    created_at: datetime
    updated_at: datetime


def _next_cell_unlock_schema(xp: int) -> NextCellUnlockSchema | None:
    unlock = get_next_cell_unlock(xp)
    if unlock is None:
        return None
    return NextCellUnlockSchema(
        unlock_xp=unlock.unlock_xp,
        unlock_level=unlock.unlock_level,
        xp_remaining=unlock.xp_remaining,
        in_current_level=unlock.in_current_level,
        bar_percent=unlock.bar_percent,
        xp_in_level_at_unlock=unlock.xp_in_level_at_unlock,
    )


def developer_public_from_orm(row: Developer) -> DeveloperPublicResponse:
    prog = get_xp_progress(row.xp_brut)
    klass = get_player_class(prog.level)
    return DeveloperPublicResponse(
        id=row.id,
        github_id=row.github_id,
        github_login=row.github_login,
        commits_alltime=row.commits_alltime,
        commits_breakdown_sum=row.commits_breakdown_sum,
        commits_farm_flagged=row.commits_farm_flagged,
        commits_farm_cleared=row.commits_farm_cleared,
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
        next_cell_unlock=_next_cell_unlock_schema(row.xp_brut),
        player_class=PlayerClassSchema(name=klass.name, phrase=klass.phrase),
        last_sync_at=row.last_sync_at,
        next_sync_at=row.last_sync_at + SYNC_COOLDOWN if row.last_sync_at else None,
        island=IslandChoice(row.island) if row.island else None,
        is_onboarded=row.is_onboarded,
        avatar_url=row.avatar_url,
        github_org_access_enabled=has_github_org_oauth_scope(row.github_oauth_scopes),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
