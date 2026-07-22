from typing import Literal

from pydantic import BaseModel


class MeReadmeResponse(BaseModel):
    content: str
    source: Literal["github", "empty"]
