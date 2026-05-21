"""add island and is_onboarded to developers

Revision ID: b8d4f2a1c7e9
Revises: f1c2d3e4b5a6
Create Date: 2026-05-21 17:07:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4f2a1c7e9"
down_revision: str | None = "f1c2d3e4b5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("developers", sa.Column("island", sa.String(50), nullable=True))
    op.add_column(
        "developers",
        sa.Column(
            "is_onboarded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("developers", "is_onboarded")
    op.drop_column("developers", "island")
