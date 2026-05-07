from typing import Annotated

from fastapi import APIRouter, Depends
from starlette import status

from app.core.github_errors import call_with_github_error_mapping
from app.dependencies.providers import get_github_score_service
from app.schemas.score import GitHubPublicScoreResponse, public_score_response_from
from app.services.github_score_service import GitHubScoreService

router = APIRouter(prefix="/github", tags=["score-github"])


@router.get(
    "/{username}/score",
    response_model=GitHubPublicScoreResponse,
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
    service: Annotated[GitHubScoreService, Depends(get_github_score_service)],
) -> GitHubPublicScoreResponse:
    snapshot = await call_with_github_error_mapping(service.build_public_snapshot(username))
    return public_score_response_from(snapshot)
