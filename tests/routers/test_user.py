from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.domain.scoring import get_cell_count
from tests.factories.developer_factory import make_developer


@pytest.mark.asyncio
async def test_get_user_returns_developer_snapshot(api_client) -> None:
    dev = make_developer(github_login="alice")

    with patch("app.routers.user.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_login = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        resp = await api_client.get("/api/v1/user/alice")

    assert resp.status_code == 200
    data = resp.json()
    assert data["github_login"] == "alice"
    assert data["github_id"] == dev.github_id
    assert "xp_brut" in data
    assert data["xp_progress"]["level"] == 1
    assert data["xp_progress"]["xp_in_level"] == 0
    assert data["xp_progress"]["percent"] == 0
    assert data["cell_count"] == get_cell_count(dev.xp_brut)
    assert data["player_class"]["name"] == "Seedling"
    assert "phrase" in data["player_class"]


@pytest.mark.asyncio
async def test_get_user_404_when_missing(api_client) -> None:
    with patch("app.routers.user.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_login = AsyncMock(return_value=None)
        RepoCls.return_value = repo

        resp = await api_client.get("/api/v1/user/ghost")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_user_case_insensitive_matches_lower_index(api_client) -> None:
    dev = make_developer(github_login="AliceMixed")

    with patch("app.routers.user.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_login = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        resp = await api_client.get("/api/v1/user/AliceMixed")

    assert resp.status_code == 200
    repo_get = RepoCls.return_value.get_by_github_login
    repo_get.assert_awaited_once()
    assert repo_get.await_args.args[0] == "AliceMixed"


@pytest.mark.asyncio
async def test_get_user_400_only_whitespace(api_client) -> None:
    resp = await api_client.get("/api/v1/user/%20")
    assert resp.status_code == 400
