from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domain.scoring import LEVEL_XP_THRESHOLDS

router = APIRouter(prefix="/xp", tags=["xp"])


@router.get("/config")
def get_xp_config() -> JSONResponse:
    """Returns XP thresholds per level.
    level_thresholds[i] = XP required to reach level i+1.
    Computed once at startup — O(1) to serve.
    """
    return JSONResponse(
        content={"level_thresholds": list(LEVEL_XP_THRESHOLDS)},
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
