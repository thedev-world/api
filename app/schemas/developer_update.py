from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domain.island import IslandChoice


class DeveloperProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    island: IslandChoice | None = None


class IslandOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str


class IslandListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    islands: list[IslandOption]
