from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.models.developer import Developer
from app.repositories.developer import DeveloperRepository
from app.schemas.developer_update import DeveloperProfileUpdateRequest


class DeveloperService:
    async def update_profile(
        self,
        db: AsyncSession,
        developer: Developer,
        payload: DeveloperProfileUpdateRequest,
    ) -> Developer:
        repo = DeveloperRepository(db)
        fields = payload.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(tz=UTC)
        await repo.update(developer, **fields)
        await db.commit()
        await db.refresh(developer)
        return developer

    async def complete_onboarding(
        self,
        db: AsyncSession,
        developer: Developer,
    ) -> Developer:
        if not developer.island:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Island must be set before completing onboarding.",
            )
        repo = DeveloperRepository(db)
        await repo.update(developer, is_onboarded=True, updated_at=datetime.now(tz=UTC))
        await db.commit()
        await db.refresh(developer)
        return developer

    async def delete_account(self, db: AsyncSession, developer: Developer) -> None:
        repo = DeveloperRepository(db)
        await repo.delete(developer)
        await db.commit()
