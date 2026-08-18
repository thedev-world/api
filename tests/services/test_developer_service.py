from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.domain.island import IslandChoice
from app.schemas.developer_update import DeveloperProfileUpdateRequest
from app.services.developer_service import DeveloperService
from fastapi import HTTPException
from tests.factories.developer_factory import make_developer


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_update_profile_sets_island() -> None:
    dev = make_developer(island=None)
    db = _mock_db()
    svc = DeveloperService()
    payload = DeveloperProfileUpdateRequest(island=IslandChoice.FRONTEND)

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.update = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        await svc.update_profile(db, dev, payload)

        kwargs = repo.update.call_args.kwargs
        assert kwargs["island"] == IslandChoice.FRONTEND
        assert "updated_at" in kwargs
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(dev)


@pytest.mark.asyncio
async def test_update_profile_exclude_unset_does_not_send_island() -> None:
    dev = make_developer(island="backend")
    db = _mock_db()
    svc = DeveloperService()
    payload = DeveloperProfileUpdateRequest()  # no fields explicitly set

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.update = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        await svc.update_profile(db, dev, payload)

        kwargs = repo.update.call_args.kwargs
        assert "island" not in kwargs
        assert "updated_at" in kwargs


@pytest.mark.asyncio
async def test_update_profile_can_set_island_to_none() -> None:
    dev = make_developer(island="frontend")
    db = _mock_db()
    svc = DeveloperService()
    payload = DeveloperProfileUpdateRequest(island=None)

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.update = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        await svc.update_profile(db, dev, payload)

        kwargs = repo.update.call_args.kwargs
        assert "island" in kwargs
        assert kwargs["island"] is None


@pytest.mark.asyncio
async def test_complete_onboarding_sets_is_onboarded_true() -> None:
    dev = make_developer(island="frontend", is_onboarded=False)
    db = _mock_db()
    svc = DeveloperService()

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.update = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        await svc.complete_onboarding(db, dev)

        kwargs = repo.update.call_args.kwargs
        assert kwargs["is_onboarded"] is True
        assert "updated_at" in kwargs
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(dev)


@pytest.mark.asyncio
async def test_complete_onboarding_does_not_touch_island() -> None:
    dev = make_developer(island="data", is_onboarded=False)
    db = _mock_db()
    svc = DeveloperService()

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.update = AsyncMock(return_value=dev)
        RepoCls.return_value = repo

        await svc.complete_onboarding(db, dev)

        kwargs = repo.update.call_args.kwargs
        assert "island" not in kwargs


@pytest.mark.asyncio
async def test_complete_onboarding_raises_422_when_island_not_set() -> None:
    dev = make_developer(island=None, is_onboarded=False)
    db = _mock_db()
    svc = DeveloperService()

    with pytest.raises(HTTPException) as exc_info:
        await svc.complete_onboarding(db, dev)

    assert exc_info.value.status_code == 422
    assert "island" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_account_hard_deletes_developer() -> None:
    dev = make_developer(island="frontend", is_onboarded=True)
    db = _mock_db()
    svc = DeveloperService()

    with patch("app.services.developer_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.delete = AsyncMock()
        RepoCls.return_value = repo

        await svc.delete_account(db, dev)

        repo.delete.assert_awaited_once_with(dev)
        db.commit.assert_awaited_once()
