"""Initial empty revision.

Revision ID: 7b2c1f4a9e3d
Revises:
Create Date: 2026-05-04

"""

from collections.abc import Sequence

revision: str = "7b2c1f4a9e3d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
