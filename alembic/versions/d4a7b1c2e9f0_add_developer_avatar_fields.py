"""add avatar_url to developers

Revision ID: d4a7b1c2e9f0
Revises: c9e5f3b2a1d8
Create Date: 2026-06-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a7b1c2e9f0"
down_revision: str | Sequence[str] | None = "c9e5f3b2a1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("developers", sa.Column("avatar_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("developers", "avatar_url")
