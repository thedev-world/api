from __future__ import annotations

import pytest
from app.config import Settings, get_settings
from app.main import app
from httpx import AsyncClient


def _make_settings(**overrides: str) -> Settings:
    base = {
        "s3_endpoint_url": "http://minio:9000",
        "s3_public_base_url": "http://localhost:9000",
        "s3_bucket_name": "devplanet",
        "s3_planet_json_key": "planet-data.json",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_planet_returns_302(api_client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _make_settings()

    resp = await api_client.get("/api/v1/planet", follow_redirects=False)

    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_get_planet_redirect_url_contains_key(api_client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _make_settings()

    resp = await api_client.get("/api/v1/planet", follow_redirects=False)

    assert "planet-data.json" in resp.headers["location"]


@pytest.mark.asyncio
async def test_get_planet_redirect_uses_public_base_url(api_client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _make_settings(
        s3_public_base_url="https://cdn.example.com"
    )

    resp = await api_client.get("/api/v1/planet", follow_redirects=False)

    assert resp.headers["location"].startswith("https://cdn.example.com")


@pytest.mark.asyncio
async def test_get_planet_falls_back_to_endpoint_url_when_public_url_empty(
    api_client: AsyncClient,
) -> None:
    app.dependency_overrides[get_settings] = lambda: _make_settings(
        s3_endpoint_url="http://minio:9000",
        s3_public_base_url="",
    )

    resp = await api_client.get("/api/v1/planet", follow_redirects=False)

    assert resp.headers["location"].startswith("http://minio:9000")


@pytest.mark.asyncio
async def test_get_planet_no_trailing_slash_in_redirect(api_client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: _make_settings(
        s3_public_base_url="http://localhost:9000/",
    )

    resp = await api_client.get("/api/v1/planet", follow_redirects=False)
    location = resp.headers["location"]

    assert "//" not in location.replace("http://", "").replace("https://", "")
