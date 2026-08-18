import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import Response

from app.clients.github import GitHubClient
from app.config import Settings, get_settings
from app.core.auth_cookies import logout_response
from app.database import get_db
from app.dependencies.auth import get_current_developer
from app.dependencies.providers import (
    get_developer_service,
    get_github_client,
    get_score_sync_service,
)
from app.domain.score_snapshot import SyncProgress
from app.models.developer import Developer
from app.schemas.developer_public import DeveloperPublicResponse, developer_public_from_orm
from app.schemas.developer_update import DeveloperProfileUpdateRequest
from app.schemas.me_readme import MeReadmeResponse
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
from app.workers.celery_app import celery
from app.workers.planet_task import update_planet_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"], redirect_slashes=False)


@router.get("", response_model=DeveloperPublicResponse)
@router.get("/", response_model=DeveloperPublicResponse)
async def get_me(
    developer: Annotated[Developer, Depends(get_current_developer)],
) -> DeveloperPublicResponse:
    return developer_public_from_orm(developer)


@router.get("/readme", response_model=MeReadmeResponse)
async def get_me_readme(
    developer: Annotated[Developer, Depends(get_current_developer)],
    github: Annotated[GitHubClient, Depends(get_github_client)],
) -> MeReadmeResponse:
    client = github.with_token(developer.github_token)
    content = await client.fetch_profile_readme(developer.github_login)
    if content is None:
        return MeReadmeResponse(content="", source="empty")
    return MeReadmeResponse(content=content, source="github")


@router.patch("", response_model=DeveloperPublicResponse)
async def update_me(
    payload: DeveloperProfileUpdateRequest,
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[DeveloperService, Depends(get_developer_service)],
) -> DeveloperPublicResponse:
    updated = await service.update_profile(db, developer, payload)
    return developer_public_from_orm(updated)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[DeveloperService, Depends(get_developer_service)],
) -> Response:
    await service.delete_account(db, developer)
    if developer.is_onboarded:
        update_planet_json.delay()
    return logout_response(settings)


@router.post("/onboarding", response_model=DeveloperPublicResponse, status_code=200)
async def complete_onboarding(
    developer: Annotated[Developer, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[DeveloperService, Depends(get_developer_service)],
) -> DeveloperPublicResponse:
    updated = await service.complete_onboarding(db, developer)
    update_planet_json.delay()
    celery.send_task(
        "devplanet.workers.generate_profile_capture",
        args=[developer.github_login],
        queue="capture",
    )
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
            private_activity=b_after.from_private_contributions
            - b_before.from_private_contributions,
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

    cells_changed = result.first_sync or (
        result.progress is not None and result.progress.cell_after != result.progress.cell_before
    )
    if cells_changed and developer.is_onboarded:
        update_planet_json.delay()
        celery.send_task(
            "devplanet.workers.generate_profile_capture",
            args=[developer.github_login],
            queue="capture",
        )
    return _performed(result)
