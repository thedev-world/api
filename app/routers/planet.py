from __future__ import annotations

from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.s3 import get_s3_client
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


@router.get("/planet")
def get_planet(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    try:
        obj = get_s3_client().get_object(
            Bucket=settings.s3_bucket_name, Key=settings.s3_planet_json_key
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NoSuchKey", "404", "NoSuchBucket"}:
            raise HTTPException(status_code=404, detail="Planet data not found") from exc
        raise

    return Response(
        content=obj["Body"].read(),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=60"},
    )
