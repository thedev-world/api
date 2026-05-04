from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.database import get_db
from app.schemas.health import HealthResponse
from app.services.health_service import check_database

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Service unhealthy"}},
)
async def health_check(session: Annotated[AsyncSession, Depends(get_db)]) -> HealthResponse:
    db_ok = await check_database(session)
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": False},
        )
    return HealthResponse(status="ok", database=True)
