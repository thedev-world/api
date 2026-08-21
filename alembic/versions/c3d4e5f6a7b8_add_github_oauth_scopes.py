"""add github_oauth_scopes on developers

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "developers",
        sa.Column("github_oauth_scopes", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("developers", "github_oauth_scopes")
