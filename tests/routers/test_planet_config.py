from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.main import app
from app.repositories.planet_config import PlanetConfigRepository
from app.routers.planet import get_planet_config_repository
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_planet_config_returns_goal(api_client: AsyncClient) -> None:
    repo = AsyncMock(spec=PlanetConfigRepository)
    repo.get_developer_goal.return_value = 500
    app.dependency_overrides[get_planet_config_repository] = lambda: repo

    response = await api_client.get("/api/v1/planet/config")

    assert response.status_code == 200
    assert response.json() == {"developer_goal": 500}


@pytest.mark.asyncio
async def test_get_planet_config_is_cached(api_client: AsyncClient) -> None:
    repo = AsyncMock(spec=PlanetConfigRepository)
    repo.get_developer_goal.return_value = 500
    app.dependency_overrides[get_planet_config_repository] = lambda: repo

    response = await api_client.get("/api/v1/planet/config")

    assert response.status_code == 200
    assert "max-age=86400" in response.headers.get("cache-control", "")
