from unittest.mock import AsyncMock

import pytest
from app.clients.github import GitHubClient
from app.dependencies.auth import get_current_developer
from app.dependencies.providers import get_github_client
from app.main import app
from app.models.developer import Developer


@pytest.fixture
def _logged_in_alice() -> None:
    alice = Developer(
        github_id=42,
        github_login="alice",
    )

    async def _dev() -> Developer:
        return alice

    app.dependency_overrides[get_current_developer] = _dev
    yield
    app.dependency_overrides.pop(get_current_developer, None)


@pytest.mark.asyncio
async def test_me_readme_requires_auth(api_client) -> None:
    resp = await api_client.get("/api/v1/me/readme")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_readme_returns_github_content(api_client, _logged_in_alice) -> None:
    mock_github = AsyncMock(spec=GitHubClient)
    mock_github.with_token.return_value = mock_github
    mock_github.fetch_profile_readme = AsyncMock(return_value="# My README")

    app.dependency_overrides[get_github_client] = lambda: mock_github

    try:
        resp = await api_client.get("/api/v1/me/readme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "# My README"
        assert data["source"] == "github"
        mock_github.with_token.assert_called_once()
        mock_github.fetch_profile_readme.assert_awaited_once_with("alice")
    finally:
        app.dependency_overrides.pop(get_github_client, None)


@pytest.mark.asyncio
async def test_me_readme_returns_empty_when_no_profile_repo(api_client, _logged_in_alice) -> None:
    mock_github = AsyncMock(spec=GitHubClient)
    mock_github.with_token.return_value = mock_github
    mock_github.fetch_profile_readme = AsyncMock(return_value=None)

    app.dependency_overrides[get_github_client] = lambda: mock_github

    try:
        resp = await api_client.get("/api/v1/me/readme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == ""
        assert data["source"] == "empty"
    finally:
        app.dependency_overrides.pop(get_github_client, None)
