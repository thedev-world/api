from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from app.clients.github import (
    GitHubAPIError,
    GitHubClient,
    GitHubRateLimitError,
    GitHubUserNotFoundError,
)
from app.config import Settings, get_settings
from app.schemas.score import GithubPublicScoreResponse, public_score_response_from
from app.services.github_score_service import GithubScoreService

router = APIRouter(prefix="/github", tags=["score-github"])


def get_github_client(settings: Annotated[Settings, Depends(get_settings)]) -> GitHubClient:
    return GitHubClient(settings)


def get_github_score_service(
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> GithubScoreService:
    return GithubScoreService(client)


@router.get(
    "/{username}/score",
    response_model=GithubPublicScoreResponse,
    response_model_by_alias=True,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid login"},
        status.HTTP_404_NOT_FOUND: {"description": "GitHub user not found"},
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "GitHub rate limit or quota exceeded"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Upstream GitHub or GraphQL error"},
    },
)
async def github_username_score(
    username: str,
    service: Annotated[GithubScoreService, Depends(get_github_score_service)],
) -> GithubPublicScoreResponse:
    try:
        snapshot = await service.build_public_snapshot(username)
        return public_score_response_from(snapshot)
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
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub rate limit exceeded. Retry later.",
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unexpected error from GitHub or GraphQL.",
        ) from exc
