from __future__ import annotations

from app.domain.planet_snapshot import PlanetEntry
from app.models.developer import Developer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PlanetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def fetch_planet_entries(self) -> list[PlanetEntry]:
        """Return all onboarded developers that have chosen an island"""
        result = await self.db.execute(
            select(Developer.github_login, Developer.island, Developer.xp_brut)
            .where(Developer.is_onboarded.is_(True))
            .where(Developer.island.is_not(None))
            .order_by(Developer.created_at, Developer.github_login)
        )
        return [
            PlanetEntry(login=row.github_login, island_id=str(row.island), xp_brut=row.xp_brut)
            for row in result.all()
        ]
