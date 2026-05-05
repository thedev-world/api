"""add developers table

Revision ID: a3c9e1b2d4f5
Revises: 7b2c1f4a9e3d
Create Date: 2026-02-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "a3c9e1b2d4f5"
down_revision: str | Sequence[str] | None = "7b2c1f4a9e3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "developers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("github_login", sa.String(length=255), nullable=False),
        sa.Column("commits_alltime", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "prs_contributions_alltime",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("reviews_alltime", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "stars_received_raw",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "stars_received_capped",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "account_created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("xp_brut", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_developers_github_login", "developers", ["github_login"])


def downgrade() -> None:
    op.drop_index("ix_developers_github_login", table_name="developers")
    op.drop_table("developers")
