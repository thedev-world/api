from __future__ import annotations

from app.config import Settings
from starlette import status
from starlette.responses import RedirectResponse, Response


def set_oauth_state_cookie(
    response: RedirectResponse,
    state: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.oauth_state_cookie_name,
        value=state,
        max_age=settings.oauth_state_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def set_session_cookie(
    response: RedirectResponse,
    session_token: str,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.jwt_expires_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_oauth_state_cookie(response: RedirectResponse, settings: Settings) -> None:
    response.delete_cookie(settings.oauth_state_cookie_name, path="/")


def apply_oauth_callback_cookies(
    response: RedirectResponse,
    *,
    session_jwt: str,
    settings: Settings,
) -> None:
    set_session_cookie(response, session_jwt, settings)
    clear_oauth_state_cookie(response, settings)


def logout_response(settings: Settings) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
