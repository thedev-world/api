"""add owned_non_fork_repos_count on developers

Revision ID: e7a2b903c641
Revises: a3c9e1b2d4f5
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a2b903c641"
down_revision: str | Sequence[str] | None = "a3c9e1b2d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column(
            "owned_non_fork_repos_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column(
        "developers",
        "owned_non_fork_repos_count",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("developers", "owned_non_fork_repos_count")
