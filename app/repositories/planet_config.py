from __future__ import annotations

from app.models.planet_config import (
    DEFAULT_DEVELOPER_GOAL,
    PLANET_CONFIG_SINGLETON_ID,
    PlanetConfig,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PlanetConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_developer_goal(self) -> int:
        goal = await self.db.scalar(
            select(PlanetConfig.developer_goal).where(PlanetConfig.id == PLANET_CONFIG_SINGLETON_ID)
        )
        return goal if goal is not None else DEFAULT_DEVELOPER_GOAL
