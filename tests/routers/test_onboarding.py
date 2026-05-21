from __future__ import annotations

import pytest
from app.domain.island import IslandChoice
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_islands_is_public_no_auth_required(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/onboarding/islands")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_islands_returns_all_ten(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/onboarding/islands")
    data = resp.json()
    assert len(data["islands"]) == len(IslandChoice)


@pytest.mark.asyncio
async def test_list_islands_shape(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/onboarding/islands")
    data = resp.json()
    for item in data["islands"]:
        assert "value" in item
        assert "label" in item
        assert item["label"].endswith("Island")


@pytest.mark.asyncio
async def test_list_islands_values_match_enum(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/onboarding/islands")
    data = resp.json()
    returned_values = {item["value"] for item in data["islands"]}
    expected_values = {island.value for island in IslandChoice}
    assert returned_values == expected_values
