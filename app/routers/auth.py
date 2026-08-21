from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.config import Settings, get_settings
from app.core.auth_cookies import (
    apply_oauth_callback_cookies,
    logout_response,
    set_oauth_return_to_cookie,
    set_oauth_state_cookie,
)
from app.database import get_db
from app.dependencies.providers import get_auth_service
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/start")
async def github_oauth_start(
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    return_to: str | None = None,
    prompt: str | None = None,
) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    prompt_consent = prompt == "consent"
    location = auth.build_authorize_redirect_url(state, prompt_consent=prompt_consent)
    response = RedirectResponse(url=location, status_code=status.HTTP_302_FOUND)
    set_oauth_state_cookie(response, state, settings)
    if return_to:
        trimmed = return_to.strip()
        if settings.is_redirect_url_allowed(trimmed):
            set_oauth_return_to_cookie(response, trimmed, settings)
    return response


@router.get("/github/callback")
async def github_oauth_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> RedirectResponse:
    q = request.query_params
    result = await auth.finish_github_callback(
        db,
        oauth_error=q.get("error"),
        code=q.get("code"),
        state_query=q.get("state"),
        state_cookie=request.cookies.get(settings.oauth_state_cookie_name),
        return_to=request.cookies.get(settings.oauth_return_to_cookie_name),
        settings=settings,
    )
    response = RedirectResponse(url=result.redirect_url, status_code=status.HTTP_302_FOUND)
    apply_oauth_callback_cookies(response, session_jwt=result.session_jwt, settings=settings)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    return logout_response(settings)
