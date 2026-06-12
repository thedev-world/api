from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.repositories.planet_config import PlanetConfigRepository
from app.schemas.planet_config import PlanetConfigResponse

router = APIRouter(tags=["planet"], redirect_slashes=False)


def get_planet_config_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanetConfigRepository:
    return PlanetConfigRepository(db)


@router.get("/planet/config", response_model=PlanetConfigResponse)
async def get_planet_config(
    repo: Annotated[PlanetConfigRepository, Depends(get_planet_config_repository)],
) -> JSONResponse:
    """Returns the developer goal count."""
    payload = PlanetConfigResponse(developer_goal=await repo.get_developer_goal())
    return JSONResponse(
        content=payload.model_dump(),
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@router.get("/planet", response_class=RedirectResponse, status_code=302)
async def get_planet(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Redirect to the static planet-data.json file on S3/CDN."""
    url = settings.planet_json_url
    return RedirectResponse(url=url, status_code=302)
