from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.github import GitHubAPIError
from app.config import Settings
from app.core.session_jwt import issue_session_token
from app.domain.datetime_github import parse_github_datetime
from app.models.developer import Developer
from app.repositories.developer import DeveloperRepository
from app.services.github_oauth_service import GitHubOAuthService

logger = logging.getLogger(__name__)


class BadOAuthStateError(Exception):
    pass


class MissingGitHubAccessTokenError(Exception):
    """Token exchange did not return a usable access_token."""


class GitHubOAuthProfileError(Exception):
    """GitHub /user response missing id or login."""


class GitHubOAuthProfileFetchError(Exception):
    """Upstream GitHub /user failure during OAuth (callback maps to 502)."""


class GitHubOAuthCallbackQueryError(Exception):
    """Invalid or missing GitHub OAuth callback query parameters."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class OAuthRedirectConfigError(Exception):
    """Post-login redirect URL is not under allowed_frontend_origins."""


@dataclass(frozen=True, slots=True)
class GitHubOAuthCallbackResult:
    session_jwt: str
    redirect_url: str


class AuthService:
    def __init__(
        self,
        *,
        oauth: GitHubOAuthService,
    ) -> None:
        self._oauth = oauth

    def build_authorize_redirect_url(self, state: str) -> str:
        return self._oauth.build_authorize_redirect_url(state)

    async def complete_github_oauth(
        self,
        db: AsyncSession,
        *,
        code: str,
        state_query: str,
        state_cookie: str | None,
    ) -> Developer:
        if not state_cookie or state_cookie != state_query:
            raise BadOAuthStateError()

        token_payload = await self._oauth.exchange_code_for_token(code)
        access_token = token_payload.get("access_token")
        if not access_token or not isinstance(access_token, str):
            raise MissingGitHubAccessTokenError()

        try:
            profile = await self._oauth.fetch_authenticated_user(access_token)
        except GitHubAPIError as exc:
            raise GitHubOAuthProfileFetchError() from exc

        raw_id = profile.get("id")
        if raw_id is None:
            raise GitHubOAuthProfileError("Missing user id in GitHub profile")
        github_id = int(raw_id)
        login = str(profile.get("login", "")).strip()
        if not login:
            raise GitHubOAuthProfileError("Missing login in GitHub profile")

        repo = DeveloperRepository(db)
        row = await repo.get_by_github_id(github_id)
        if row is None:
            now = datetime.now(tz=UTC)
            account_created_at = now
            raw_created = profile.get("created_at")
            if isinstance(raw_created, str) and raw_created.strip():
                try:
                    account_created_at = parse_github_datetime(raw_created)
                except ValueError:
                    account_created_at = now
            created = Developer(
                github_id=github_id,
                github_login=login,
                github_token=access_token,
                account_created_at=account_created_at,
                last_sync_at=None,
                created_at=now,
                updated_at=now,
            )
            await repo.create(created)
            await db.commit()
            await db.refresh(created)
            return created

        now = datetime.now(tz=UTC)
        updated = False
        if row.github_login != login:
            row.github_login = login
            updated = True
        if row.github_token != access_token:
            row.github_token = access_token
            updated = True
        if updated:
            row.updated_at = now
            await db.commit()
        return row

    async def finish_github_callback(
        self,
        db: AsyncSession,
        *,
        oauth_error: str | None,
        code: str | None,
        state_query: str | None,
        state_cookie: str | None,
        settings: Settings,
    ) -> GitHubOAuthCallbackResult:
        if oauth_error:
            raise GitHubOAuthCallbackQueryError(f"GitHub OAuth error: {oauth_error}")
        if not code or not state_query:
            raise GitHubOAuthCallbackQueryError("Missing OAuth code or state")

        target = settings.effective_post_login_redirect
        if not settings.is_redirect_url_allowed(target):
            logger.error("Configured post-login redirect is not allowlisted: %s", target)
            raise OAuthRedirectConfigError()

        developer = await self.complete_github_oauth(
            db,
            code=code,
            state_query=state_query,
            state_cookie=state_cookie,
        )
        session_jwt = issue_session_token(developer_id=developer.id, settings=settings)
        return GitHubOAuthCallbackResult(session_jwt=session_jwt, redirect_url=target)
