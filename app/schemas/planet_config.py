from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlanetConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    developer_goal: int = Field(ge=1)
