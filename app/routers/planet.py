from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["planet"], redirect_slashes=False)


@router.get("/planet", response_class=RedirectResponse, status_code=302)
async def get_planet(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Redirect to the static planet-data.json file on S3/CDN."""
    url = settings.planet_json_url
    return RedirectResponse(url=url, status_code=302)
