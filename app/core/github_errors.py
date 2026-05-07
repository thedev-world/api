"""Utility to map GitHub client exceptions to FastAPI HTTPException responses."""

from __future__ import annotations

import logging
from collections.abc import Coroutine
from typing import Any

from app.clients.github import GitHubAPIError, GitHubRateLimitError, GitHubUserNotFoundError
from fastapi import HTTPException
from starlette import status

logger = logging.getLogger(__name__)

_DETAIL_MAX = 800


async def call_with_github_error_mapping[T](coro: Coroutine[Any, Any, T]) -> T:
    """Await *coro* and translate GitHub client exceptions into HTTPExceptions."""
    try:
        return await coro
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
        logger.warning("GitHub client error: %s", exc)
        detail = str(exc).strip()[:_DETAIL_MAX] or "Unexpected error from GitHub or GraphQL."
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc
