"""encrypt_github_token

Revision ID: 2c8d4e1f6a90
Revises: 1b49abb5fe87
Create Date: 2026-08-11 16:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c8d4e1f6a90"
down_revision: str | None = "1b49abb5fe87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "developers",
        "github_token",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "developers",
        "github_token",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
