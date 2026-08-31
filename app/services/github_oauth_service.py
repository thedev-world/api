from __future__ import annotations

from typing import Any

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.clients.github import GitHubAPIError
from app.config import Settings
from app.domain.github_oauth_scopes import github_oauth_scope_string


class GitHubOAuthService:
    """GitHub OAuth2 authorization-code exchange and authenticated /user fetch."""

    _AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_authorize_redirect_url(
        self,
        state: str,
        *,
        prompt_consent: bool = False,
        include_orgs: bool = False,
    ) -> str:
        client = AsyncOAuth2Client(
            client_id=self._settings.github_oauth_client_id,
            client_secret=self._settings.github_oauth_client_secret,
            scope=github_oauth_scope_string(include_orgs=include_orgs),
        )
        extra: dict[str, str] = {}
        if prompt_consent:
            extra["prompt"] = "consent"
        uri, _ = client.create_authorization_url(
            self._AUTHORIZE_URL,
            redirect_uri=self._settings.oauth_callback_url,
            state=state,
            **extra,
        )
        return uri

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        async with AsyncOAuth2Client(
            client_id=self._settings.github_oauth_client_id,
            client_secret=self._settings.github_oauth_client_secret,
        ) as client:
            token = await client.fetch_token(
                self._TOKEN_URL,
                code=code,
                redirect_uri=self._settings.oauth_callback_url,
            )
        return dict(token)

    async def fetch_authenticated_user(self, access_token: str) -> dict[str, Any]:
        base = self._settings.github_api_base.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=httpx.Timeout(45.0),
        ) as client:
            r = await client.get("/user")
        if r.status_code == 404:
            raise GitHubAPIError("GitHub user not found for OAuth token")
        if r.status_code >= 400:
            raise GitHubAPIError(f"GitHub /user HTTP {r.status_code}: {r.text}")
        data = r.json()
        if not isinstance(data, dict):
            raise GitHubAPIError("Invalid GitHub /user JSON body")
        return data
