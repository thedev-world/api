from __future__ import annotations

import pytest
from app.domain.scoring import PLAYER_CLASSES_LIST
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_player_classes_returns_all_classes_ordered_by_tier(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/xp/classes")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == len(PLAYER_CLASSES_LIST)

    tiers = [item["tier"] for item in data]
    assert tiers == sorted(tiers)


@pytest.mark.asyncio
async def test_get_player_classes_schema(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/xp/classes")
    assert response.status_code == 200

    first = response.json()[0]
    assert first["slug"] == "seedling"
    assert first["name"] == "Seedling"
    assert first["tier"] == 1
    assert first["required_level"] == 1
    assert isinstance(first["phrase"], str)


@pytest.mark.asyncio
async def test_get_player_classes_is_cached(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/xp/classes")
    assert response.status_code == 200
    assert "max-age=86400" in response.headers.get("cache-control", "")
