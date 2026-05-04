from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_returns_service_identifier(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "devplanet-api"}
