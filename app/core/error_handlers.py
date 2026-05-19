from __future__ import annotations

import logging
from typing import Any

from app.clients.github import (
    GitHubAPIError,
    GitHubRateLimitError,
    GitHubUserNotFoundError,
    InvalidGitHubLoginError,
)
from app.services.auth_service import (
    BadOAuthStateError,
    GitHubOAuthCallbackQueryError,
    GitHubOAuthProfileError,
    GitHubOAuthProfileFetchError,
    MissingGitHubAccessTokenError,
    OAuthRedirectConfigError,
)
from authlib.integrations.base_client.errors import OAuthError
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette import status

logger = logging.getLogger(__name__)

_DETAIL_MAX = 800


def register_github_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidGitHubLoginError)
    async def _invalid_login(_request: Any, _exc: InvalidGitHubLoginError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid login"},
        )

    @app.exception_handler(GitHubUserNotFoundError)
    async def _user_not_found(_request: Any, _exc: GitHubUserNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "GitHub user not found"},
        )

    @app.exception_handler(GitHubRateLimitError)
    async def _rate_limit(_request: Any, _exc: GitHubRateLimitError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "GitHub rate limit exceeded. Retry later."},
        )

    @app.exception_handler(GitHubAPIError)
    async def _api_err(_request: Any, exc: GitHubAPIError) -> JSONResponse:
        logger.warning("GitHub client error: %s", exc)
        detail = str(exc).strip()[:_DETAIL_MAX] or "Unexpected error from GitHub or GraphQL."
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": detail},
        )


def register_auth_oauth_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BadOAuthStateError)
    async def _bad_state(_request: Any, _exc: BadOAuthStateError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid OAuth state"},
        )

    @app.exception_handler(OAuthError)
    async def _oauth_err(_request: Any, exc: OAuthError) -> JSONResponse:
        logger.warning("GitHub token exchange failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "GitHub OAuth token exchange failed"},
        )

    @app.exception_handler(MissingGitHubAccessTokenError)
    async def _missing_token(
        _request: Any,
        _exc: MissingGitHubAccessTokenError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "GitHub did not return an access token"},
        )

    @app.exception_handler(GitHubOAuthProfileError)
    async def _bad_profile(
        _request: Any,
        exc: GitHubOAuthProfileError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exc) or "Invalid GitHub user profile"},
        )

    @app.exception_handler(GitHubOAuthProfileFetchError)
    async def _profile_fetch(
        _request: Any,
        exc: GitHubOAuthProfileFetchError,
    ) -> JSONResponse:
        if exc.__cause__ is not None:
            logger.warning("GitHub API error during OAuth: %s", exc.__cause__)
        else:
            logger.warning("GitHub API error during OAuth profile fetch")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Could not load GitHub profile"},
        )

    @app.exception_handler(GitHubOAuthCallbackQueryError)
    async def _bad_query(
        _request: Any,
        exc: GitHubOAuthCallbackQueryError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.detail},
        )

    @app.exception_handler(OAuthRedirectConfigError)
    async def _bad_redirect_config(
        _request: Any,
        _exc: OAuthRedirectConfigError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Invalid OAuth redirect configuration"},
        )
