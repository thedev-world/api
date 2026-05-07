"""Read persisted developer by GitHub login."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from app.dependencies.providers import get_developer_repository
from app.repositories.developer import DeveloperRepository
from app.schemas.developer_public import DeveloperPublicResponse, developer_public_from_orm

router = APIRouter(prefix="/user", tags=["user"])


@router.get(
    "/{github_login}",
    response_model=DeveloperPublicResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Empty or whitespace login"},
        status.HTTP_404_NOT_FOUND: {"description": "Developer not synced yet"},
    },
)
async def get_developer_by_github_login(
    github_login: str,
    repo: Annotated[DeveloperRepository, Depends(get_developer_repository)],
) -> DeveloperPublicResponse:
    stripped = github_login.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub login cannot be empty",
        )

    row = await repo.get_by_github_login(stripped)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Developer not found",
        )
    return developer_public_from_orm(row)
