"""add commits farm detection fields on developers

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column(
            "commits_breakdown_sum",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "developers",
        sa.Column(
            "commits_farm_flagged",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "developers",
        sa.Column(
            "commits_farm_cleared",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.alter_column("developers", "commits_breakdown_sum", server_default=None)
    op.alter_column("developers", "commits_farm_flagged", server_default=None)
    op.alter_column("developers", "commits_farm_cleared", server_default=None)


def downgrade() -> None:
    op.drop_column("developers", "commits_farm_cleared")
    op.drop_column("developers", "commits_farm_flagged")
    op.drop_column("developers", "commits_breakdown_sum")
