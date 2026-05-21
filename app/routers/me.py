import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_developer
from app.dependencies.providers import get_developer_service, get_score_sync_service
from app.domain.score_snapshot import SyncProgress
from app.models.developer import Developer
from app.schemas.developer_public import DeveloperPublicResponse, developer_public_from_orm
from app.schemas.developer_update import DeveloperProfileUpdateRequest
from app.schemas.score import (
    XpProgressSchema,
    public_score_response_from,
)
from app.schemas.sync_score import (
    MeSyncCooldownResponse,
    MeSyncPerformedResponse,
    MeSyncUnionResponse,
    ScoreSyncProgressSchema,
    ScoreXpBreakdownDeltaSchema,
)
from app.services.developer_service import DeveloperService
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"], redirect_slashes=False)


@router.get("", response_model=DeveloperPublicResponse)
@router.get("/", response_model=DeveloperPublicResponse)
async def get_me(
    developer: Annotated[Developer, Depends(get_current_developer)],
) -> DeveloperPublicResponse:
    return developer_public_from_orm(developer)


@router.patch("", response_model=DeveloperPublicResponse)
async def update_me(
    payload: DeveloperProfileUpdateRequest,
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[DeveloperService, Depends(get_developer_service)],
) -> DeveloperPublicResponse:
    updated = await service.update_profile(db, developer, payload)
    return developer_public_from_orm(updated)


@router.post("/onboarding", response_model=DeveloperPublicResponse, status_code=200)
async def complete_onboarding(
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[DeveloperService, Depends(get_developer_service)],
) -> DeveloperPublicResponse:
    updated = await service.complete_onboarding(db, developer)
    return developer_public_from_orm(updated)


def _map_sync_progress(progress: SyncProgress) -> ScoreSyncProgressSchema:
    b_before = progress.breakdown_before
    b_after = progress.breakdown_after
    return ScoreSyncProgressSchema(
        xp_before=progress.xp_before,
        xp_after=progress.xp_after,
        level_before=progress.level_before,
        level_after=progress.level_after,
        cell_before=progress.cell_before,
        cell_after=progress.cell_after,
        xp_progress_before=XpProgressSchema(
            level=progress.xp_progress_before.level,
            xp_in_level=progress.xp_progress_before.xp_in_level,
            xp_needed=progress.xp_progress_before.xp_needed,
            percent=progress.xp_progress_before.percent,
        ),
        xp_progress_after=XpProgressSchema(
            level=progress.xp_progress_after.level,
            xp_in_level=progress.xp_progress_after.xp_in_level,
            xp_needed=progress.xp_progress_after.xp_needed,
            percent=progress.xp_progress_after.percent,
        ),
        breakdown_delta=ScoreXpBreakdownDeltaSchema(
            commits=b_after.from_commits - b_before.from_commits,
            pull_requests=b_after.from_pull_requests - b_before.from_pull_requests,
            reviews=b_after.from_reviews - b_before.from_reviews,
            stars=b_after.from_stars - b_before.from_stars,
            forks=b_after.from_forks - b_before.from_forks,
            followers=b_after.from_followers - b_before.from_followers,
            tenure_years_bonus=b_after.from_tenure - b_before.from_tenure,
        ),
    )


def _cooldown(resp: MeSyncCooldown) -> MeSyncCooldownResponse:
    return MeSyncCooldownResponse(retry_after=resp.retry_after)


def _performed(p: MeSyncPerformed) -> MeSyncPerformedResponse:
    payload = public_score_response_from(p.snapshot)
    progress = _map_sync_progress(p.progress) if p.progress is not None else None
    return MeSyncPerformedResponse.model_validate(
        {
            **payload.model_dump(),
            "sync_performed": True,
            "first_sync": p.first_sync,
            "progress": progress,
        }
    )


@router.post(
    "/sync",
    response_model=MeSyncUnionResponse,
    response_model_by_alias=True,
)
async def me_sync_score(
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[ScoreSyncService, Depends(get_score_sync_service)],
) -> MeSyncUnionResponse:
    result = await service.sync_for_actor(
        db,
        github_id=developer.github_id,
        login=developer.github_login,
    )

    if isinstance(result, MeSyncCooldown):
        return _cooldown(result)

    return _performed(result)
