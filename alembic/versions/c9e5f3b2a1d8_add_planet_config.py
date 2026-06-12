"""add planet_config singleton table

Revision ID: c9e5f3b2a1d8
Revises: b8d4f2a1c7e9
Create Date: 2026-06-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e5f3b2a1d8"
down_revision: str | Sequence[str] | None = "b8d4f2a1c7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planet_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "developer_goal",
            sa.Integer(),
            server_default=sa.text("500"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO planet_config (id, developer_goal) VALUES (1, 500)"))


def downgrade() -> None:
    op.drop_table("planet_config")
