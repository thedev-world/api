from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.domain.scoring import LEVEL_XP_THRESHOLDS, PLAYER_CLASSES_LIST
from app.schemas.score import PlayerClassListItemSchema

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


@router.get("/classes", response_model=list[PlayerClassListItemSchema])
def get_player_classes() -> JSONResponse:
    """Returns all player classes ordered by tier.
    Computed once at startup — O(1) to serve.
    """
    data = [
        PlayerClassListItemSchema(
            slug=cls.slug,
            name=cls.name,
            tier=cls.tier,
            required_level=cls.required_level,
            phrase=cls.phrase,
        ).model_dump()
        for cls in PLAYER_CLASSES_LIST
    ]
    return JSONResponse(
        content=data,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
