from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_planet_returns_json_from_s3(api_client: AsyncClient) -> None:
    payload = b'{"updated_at":"2026-01-01","islands":{}}'
    body_mock = MagicMock()
    body_mock.read.return_value = payload

    with patch("app.routers.planet.get_s3_client") as mock_s3:
        mock_s3.return_value.get_object.return_value = {"Body": body_mock}
        resp = await api_client.get("/api/v1/planet")

    assert resp.status_code == 200
    assert resp.content == payload
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["cache-control"] == "public, max-age=60"
    mock_s3.return_value.get_object.assert_called_once_with(
        Bucket="devplanet",
        Key="planet-data.json",
    )


@pytest.mark.asyncio
async def test_get_planet_returns_404_when_s3_object_missing(api_client: AsyncClient) -> None:
    error = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
        "GetObject",
    )

    with patch("app.routers.planet.get_s3_client") as mock_s3:
        mock_s3.return_value.get_object.side_effect = error
        resp = await api_client.get("/api/v1/planet")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Planet data not found"
