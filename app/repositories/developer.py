from app.models.developer import Developer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class DeveloperRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_github_id(self, github_id: int) -> Developer | None:
        row = await self.db.scalar(select(Developer).where(Developer.github_id == github_id))
        return row

    async def get_by_github_login(self, github_login: str) -> Developer | None:
        stripped = github_login.strip()
        if not stripped:
            return None
        row = await self.db.scalar(
            select(Developer).where(func.lower(Developer.github_login) == stripped.lower())
        )
        return row

    async def create(self, developer: Developer) -> Developer:
        self.db.add(developer)
        return developer

    async def flush(self) -> None:
        await self.db.flush()
