from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.domain.planet_snapshot import PlanetEntry
from app.workers.planet_task import _fetch_and_generate, update_planet_json


@pytest.mark.asyncio
async def test_fetch_and_generate_returns_valid_json() -> None:
    entries = [
        PlanetEntry(login="alice", island_id="frontend", xp_brut=1_000),
        PlanetEntry(login="bob", island_id="backend", xp_brut=5_000),
    ]

    with (
        patch("app.workers.planet_task.create_async_engine") as mock_engine_cls,
        patch("app.workers.planet_task.async_sessionmaker") as mock_factory_cls,
        patch("app.workers.planet_task.PlanetRepository") as mock_repo_cls,
    ):
        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_ctx
        mock_factory_cls.return_value = mock_factory

        mock_repo = AsyncMock()
        mock_repo.fetch_planet_entries = AsyncMock(return_value=entries)
        mock_repo_cls.return_value = mock_repo

        result = await _fetch_and_generate("postgresql+asyncpg://test/test")

    payload = json.loads(result)
    assert "updated_at" in payload
    assert "islands" in payload
    assert "frontend" in payload["islands"]
    assert "backend" in payload["islands"]
    mock_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_generate_disposes_engine_on_error() -> None:
    with (
        patch("app.workers.planet_task.create_async_engine") as mock_engine_cls,
        patch("app.workers.planet_task.async_sessionmaker") as mock_factory_cls,
        patch("app.workers.planet_task.PlanetRepository") as mock_repo_cls,
    ):
        mock_engine = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_ctx
        mock_factory_cls.return_value = mock_factory

        mock_repo = AsyncMock()
        mock_repo.fetch_planet_entries = AsyncMock(side_effect=RuntimeError("db down"))
        mock_repo_cls.return_value = mock_repo

        with pytest.raises(RuntimeError, match="db down"):
            await _fetch_and_generate("postgresql+asyncpg://test/test")

    mock_engine.dispose.assert_awaited_once()


def test_update_planet_json_uploads_to_s3() -> None:
    fake_data = b'{"updated_at":"2026-01-01T00:00:00+00:00","islands":{"backend":[["alice",3]]}}'

    mock_s3 = MagicMock()

    async def _fake_fetch(database_url: str) -> bytes:  # noqa: ARG001
        return fake_data

    with (
        patch("app.workers.planet_task._fetch_and_generate", side_effect=_fake_fetch),
        patch("app.workers.planet_task.get_s3_client", return_value=mock_s3),
    ):
        result = update_planet_json.run()

    assert result == "ok"
    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args.kwargs
    assert call_kwargs["Body"] == fake_data
    assert call_kwargs["ContentType"] == "application/json"
    assert call_kwargs["Key"] == "planet-data.json"


def test_update_planet_json_uses_correct_bucket() -> None:
    fake_data = b'{"updated_at":"2026-01-01T00:00:00+00:00","islands":{}}'

    mock_s3 = MagicMock()

    async def _fake_fetch(database_url: str) -> bytes:  # noqa: ARG001
        return fake_data

    with (
        patch("app.workers.planet_task._fetch_and_generate", side_effect=_fake_fetch),
        patch("app.workers.planet_task.get_s3_client", return_value=mock_s3),
    ):
        update_planet_json.run()

    call_kwargs = mock_s3.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "devplanet"
