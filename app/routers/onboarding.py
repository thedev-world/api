from fastapi import APIRouter

from app.domain.island import IslandChoice
from app.schemas.developer_update import IslandListResponse, IslandOption

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/islands", response_model=IslandListResponse)
def list_islands() -> IslandListResponse:
    return IslandListResponse(
        islands=[IslandOption(value=island.value, label=island.label) for island in IslandChoice]
    )
