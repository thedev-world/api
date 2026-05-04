from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok_when_database_check_succeeds(
    api_client: AsyncClient,
    override_db_healthy: None,
) -> None:
    response = await api_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


@pytest.mark.asyncio
async def test_health_returns_503_when_database_check_fails(
    api_client: AsyncClient,
    override_db_unhealthy: None,
) -> None:
    response = await api_client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unhealthy", "database": False}}
