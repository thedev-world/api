"""unique functional index lower(github_login) on developers

Revision ID: f1c2d3e4b5a6
Revises: e7a2b903c641
Create Date: 2026-05-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f1c2d3e4b5a6"
down_revision: str | Sequence[str] | None = "e7a2b903c641"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_developers_github_login", table_name="developers")
    op.execute(
        "CREATE UNIQUE INDEX ix_developers_github_login_lower ON developers (LOWER(github_login))",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_developers_github_login_lower")
    op.create_index(
        "ix_developers_github_login",
        "developers",
        ["github_login"],
        unique=False,
    )
