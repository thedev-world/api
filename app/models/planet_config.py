from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

PLANET_CONFIG_SINGLETON_ID = 1
DEFAULT_DEVELOPER_GOAL = 500


class PlanetConfig(Base):
    __tablename__ = "planet_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    developer_goal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=str(DEFAULT_DEVELOPER_GOAL),
    )
