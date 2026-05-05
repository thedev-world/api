import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.clients.github import (
    GitHubAPIError,
    GitHubClient,
    GitHubRateLimitError,
    GitHubUserNotFoundError,
)
from app.config import Settings, get_settings
from app.database import get_db
from app.schemas.sync_score import (
    MeSyncCooldownResponse,
    MeSyncPerformedResponse,
    MeSyncRequestBody,
    MeSyncUnionResponse,
)
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["me"])

_GITHUB_ERROR_DETAIL_MAX = 800


def _github_api_error_detail(exc: GitHubAPIError) -> str:
    msg = str(exc).strip()
    if not msg:
        return "Unexpected error from GitHub or GraphQL."
    if len(msg) > _GITHUB_ERROR_DETAIL_MAX:
        return msg[:_GITHUB_ERROR_DETAIL_MAX] + "…"
    return msg


def get_github_client(settings: Annotated[Settings, Depends(get_settings)]) -> GitHubClient:
    return GitHubClient(settings)


def get_score_sync_service(
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> ScoreSyncService:
    return ScoreSyncService(client)


def _cooldown(resp: MeSyncCooldown) -> MeSyncCooldownResponse:
    return MeSyncCooldownResponse(retry_after=resp.retry_after)


def _performed(p: MeSyncPerformed) -> MeSyncPerformedResponse:
    return MeSyncPerformedResponse.model_validate(
        {
            **p.payload.model_dump(),
            "sync_performed": True,
            "first_sync": p.first_sync,
            "progress": p.progress,
        }
    )


@router.post(
    "/sync",
    response_model=MeSyncUnionResponse,
    response_model_by_alias=True,
)
async def me_sync_score(
    body: MeSyncRequestBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[ScoreSyncService, Depends(get_score_sync_service)],
) -> MeSyncUnionResponse:
    try:
        result = await service.sync_for_github_login(
            db,
            github_login=body.github_login,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid login",
        ) from exc
    except GitHubUserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub user not found",
        ) from None
    except GitHubRateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub rate limit exceeded. Retry later.",
        ) from None
    except GitHubAPIError as exc:
        logger.warning("GitHub client error during /me/sync: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_github_api_error_detail(exc),
        ) from exc

    if isinstance(result, MeSyncCooldown):
        return _cooldown(result)

    return _performed(result)
