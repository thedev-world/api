from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.dependencies.providers import get_auth_service
from app.main import app
from app.models.developer import Developer
from app.services.auth_service import AuthService, BadOAuthStateError


@pytest.mark.asyncio
async def test_github_oauth_start_redirect_and_state_cookie(api_client) -> None:
    class _Svc(AuthService):
        def build_authorize_redirect_url(self, state: str) -> str:
            assert len(state) >= 8
            return "https://github.com/login/oauth/authorize?client_id=x"

    app.dependency_overrides[get_auth_service] = lambda: _Svc(oauth=MagicMock())

    try:
        response = await api_client.get(
            "/api/v1/auth/github/start",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("https://github.com/login/oauth/authorize")
        assert "github_oauth_state" in response.cookies
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


@pytest.mark.asyncio
async def test_github_oauth_callback_invalid_state(api_client) -> None:
    api_client.cookies.set("github_oauth_state", "right", path="/", domain="test")
    response = await api_client.get(
        "/api/v1/auth/github/callback",
        params={"code": "abc", "state": "wrong"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_github_oauth_callback_success_sets_session_cookie(api_client) -> None:
    dev = MagicMock(spec=Developer)
    dev.id = uuid4()

    class _Svc(AuthService):
        async def complete_github_oauth(self, db, **kwargs):  # type: ignore[no-untyped-def]
            _ = (db, kwargs)
            return dev

    app.dependency_overrides[get_auth_service] = lambda: _Svc(oauth=MagicMock())

    try:
        api_client.cookies.set("github_oauth_state", "s3cret", path="/", domain="test")
        response = await api_client.get(
            "/api/v1/auth/github/callback",
            params={"code": "exchange-code", "state": "s3cret"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:3000/"
        assert "devplanet_session" in response.cookies
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


@pytest.mark.asyncio
async def test_github_oauth_callback_propagates_service_state_error(api_client) -> None:
    class _Svc(AuthService):
        async def complete_github_oauth(self, db, **kwargs):  # type: ignore[no-untyped-def]
            _ = (db, kwargs)
            raise BadOAuthStateError()

    app.dependency_overrides[get_auth_service] = lambda: _Svc(oauth=MagicMock())

    try:
        api_client.cookies.set("github_oauth_state", "s", path="/", domain="test")
        response = await api_client.get(
            "/api/v1/auth/github/callback",
            params={"code": "x", "state": "s"},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


@pytest.mark.asyncio
async def test_logout_clears_session_cookie(api_client) -> None:
    response = await api_client.post("/api/v1/auth/logout")
    assert response.status_code == 204
