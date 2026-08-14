"""add private_contributions_alltime on developers

Revision ID: a1b2c3d4e5f6
Revises: f1c2d3e4b5a6
Create Date: 2026-08-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "2c8d4e1f6a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column(
            "private_contributions_alltime",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column(
        "developers",
        "private_contributions_alltime",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("developers", "private_contributions_alltime")
