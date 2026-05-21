from __future__ import annotations

from typing import Annotated

from app.clients.github import GitHubClient
from app.config import Settings, get_settings
from app.database import get_db
from app.repositories.developer import DeveloperRepository
from app.services.auth_service import AuthService
from app.services.developer_service import DeveloperService
from app.services.github_oauth_service import GitHubOAuthService
from app.services.github_score_service import GitHubScoreService
from app.services.score_sync_service import ScoreSyncService
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


def get_github_client(settings: Annotated[Settings, Depends(get_settings)]) -> GitHubClient:
    return GitHubClient(settings)


def get_score_sync_service(
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> ScoreSyncService:
    return ScoreSyncService(client)


def get_github_oauth_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitHubOAuthService:
    return GitHubOAuthService(settings)


def get_auth_service(
    oauth: Annotated[GitHubOAuthService, Depends(get_github_oauth_service)],
) -> AuthService:
    return AuthService(oauth=oauth)


def get_github_score_service(
    client: Annotated[GitHubClient, Depends(get_github_client)],
) -> GitHubScoreService:
    return GitHubScoreService(client)


def get_developer_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeveloperRepository:
    return DeveloperRepository(db)


def get_developer_service() -> DeveloperService:
    return DeveloperService()
