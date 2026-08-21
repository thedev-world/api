from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.clients.github import GitHubClient
from app.config import Settings


def _settings(**overrides: object) -> Settings:
    base = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "github_oauth_client_id": "cid",
        "github_oauth_client_secret": "sec",
        "oauth_callback_url": "http://test/callback",
        "jwt_secret_key": "unit-test-jwt-secret-key-32-bytes-min",
        "token_encryption_key": "UaFsQc-_TszKnclBK2EtbZy_-i88lwSAXRC1Cd4-kA0=",
        "s3_access_key": "key",
        "s3_secret_key": "secret",
    }
    base.update(overrides)
    return Settings(**base)


_PERSONAL_REPO = {
    "full_name": "octocat/personal",
    "stargazers_count": 7,
    "forks_count": 1,
    "fork": False,
}


def _json_response(payload: object, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/test")
    return httpx.Response(status_code, json=payload, request=request)


@pytest.mark.asyncio
async def test_fetch_owner_repo_star_fork_totals_includes_org_admin_repos() -> None:
    client = GitHubClient(_settings(), token="user-oauth-token")

    async def _route(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/users/octocat/repos":
            return _json_response([_PERSONAL_REPO])
        if path == "/user/memberships/orgs":
            return _json_response(
                [
                    {
                        "role": "admin",
                        "organization": {"login": "ferriskey"},
                    },
                    {
                        "role": "member",
                        "organization": {"login": "other-org"},
                    },
                ]
            )
        if path == "/orgs/ferriskey/repos":
            return _json_response(
                [
                    {
                        "full_name": "ferriskey/ferriskey",
                        "stargazers_count": 682,
                        "forks_count": 40,
                        "fork": False,
                    }
                ]
            )
        raise AssertionError(f"unexpected path: {path}")

    transport = httpx.MockTransport(_route)
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.github.com",
    )
    mock_async_client.__aexit__.return_value = False

    with patch.object(client, "_open_client", return_value=mock_async_client):
        stars, forks = await client.fetch_owner_repo_star_fork_totals(
            "octocat",
            include_org_admin_repos=True,
        )

    assert stars == (7, 682)
    assert forks == 41


@pytest.mark.asyncio
async def test_fetch_owner_repo_star_fork_totals_personal_only_when_org_disabled() -> None:
    client = GitHubClient(_settings(), token="user-oauth-token")

    async def _route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/octocat/repos":
            return _json_response([_PERSONAL_REPO])
        raise AssertionError(f"unexpected path: {request.url.path}")

    transport = httpx.MockTransport(_route)
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.github.com",
    )
    mock_async_client.__aexit__.return_value = False

    with patch.object(client, "_open_client", return_value=mock_async_client):
        stars, forks = await client.fetch_owner_repo_star_fork_totals(
            "octocat",
            include_org_admin_repos=False,
        )

    assert stars == (7,)
    assert forks == 1


def _admin_membership(org_login: str) -> dict[str, object]:
    return {"role": "admin", "organization": {"login": org_login}}


@pytest.mark.asyncio
async def test_fetch_owner_repo_star_fork_totals_paginates_org_memberships() -> None:
    client = GitHubClient(_settings(), token="user-oauth-token")
    page1_orgs = [f"org-{i}" for i in range(100)]
    page2_orgs = ["org-100", "org-101"]

    async def _route(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/users/octocat/repos":
            return _json_response([])
        if path == "/user/memberships/orgs":
            page = int(request.url.params.get("page", "1"))
            if page == 1:
                return _json_response([_admin_membership(login) for login in page1_orgs])
            if page == 2:
                return _json_response([_admin_membership(login) for login in page2_orgs])
            return _json_response([])
        if path.startswith("/orgs/") and path.endswith("/repos"):
            org_login = path.removeprefix("/orgs/").removesuffix("/repos")
            return _json_response(
                [
                    {
                        "full_name": f"{org_login}/main",
                        "stargazers_count": 1,
                        "forks_count": 0,
                        "fork": False,
                    }
                ]
            )
        raise AssertionError(f"unexpected path: {path}")

    transport = httpx.MockTransport(_route)
    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.github.com",
    )
    mock_async_client.__aexit__.return_value = False

    with patch.object(client, "_open_client", return_value=mock_async_client):
        stars, forks = await client.fetch_owner_repo_star_fork_totals(
            "octocat",
            include_org_admin_repos=True,
        )

    assert len(stars) == 102
    assert sum(stars) == 102
    assert forks == 0
