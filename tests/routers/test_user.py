from unittest.mock import AsyncMock, MagicMock

import pytest
from app.dependencies.providers import get_developer_repository
from app.domain.scoring import get_cell_count
from app.main import app
from tests.factories.developer_factory import make_developer


def _repo_override(return_value):
    repo = MagicMock()
    repo.get_by_github_login = AsyncMock(return_value=return_value)
    app.dependency_overrides[get_developer_repository] = lambda: repo
    return repo


def _cleanup():
    app.dependency_overrides.pop(get_developer_repository, None)


@pytest.mark.asyncio
async def test_get_user_returns_developer_snapshot(api_client) -> None:
    dev = make_developer(
        github_login="alice",
        commits_breakdown_sum=800,
        commits_farm_flagged=True,
        commits_farm_cleared=False,
    )
    repo = _repo_override(dev)

    try:
        resp = await api_client.get("/api/v1/user/alice")
    finally:
        _cleanup()

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
    assert data["commits_breakdown_sum"] == 800
    assert data["commits_farm_flagged"] is True
    assert data["commits_farm_cleared"] is False
    repo.get_by_github_login.assert_awaited_once_with("alice")


@pytest.mark.asyncio
async def test_get_user_404_when_missing(api_client) -> None:
    _repo_override(None)

    try:
        resp = await api_client.get("/api/v1/user/ghost")
    finally:
        _cleanup()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_user_case_insensitive_matches_lower_index(api_client) -> None:
    dev = make_developer(github_login="AliceMixed")
    repo = _repo_override(dev)

    try:
        resp = await api_client.get("/api/v1/user/AliceMixed")
    finally:
        _cleanup()

    assert resp.status_code == 200
    repo.get_by_github_login.assert_awaited_once_with("AliceMixed")


@pytest.mark.asyncio
async def test_get_user_400_only_whitespace(api_client) -> None:
    resp = await api_client.get("/api/v1/user/%20")
    assert resp.status_code == 400
