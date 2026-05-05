from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Developer(Base):
    __tablename__ = "developers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)

    commits_alltime: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prs_contributions_alltime: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviews_alltime: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    forks_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars_received_raw: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars_received_capped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owned_non_fork_repos_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    account_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    xp_brut: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_developers_github_login_lower",
            func.lower(github_login),
            unique=True,
        ),
    )
