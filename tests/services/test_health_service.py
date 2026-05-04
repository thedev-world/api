from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.health_service import check_database
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_check_database_returns_true_when_query_succeeds() -> None:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())

    assert await check_database(session) is True


@pytest.mark.asyncio
async def test_check_database_returns_false_when_query_errors() -> None:
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=RuntimeError("connection refused"))

    assert await check_database(session) is False
