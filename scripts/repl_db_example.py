#!/usr/bin/env python3
"""Set ``Developer.last_sync_at`` to (UTC now - hours) for POST /api/v1/me/sync testing.

Only ``last_sync_at`` is updated; aggregates (``commits_alltime``, …) stay as after the last real
sync. Advancing ``last_sync_at`` into the past then running incremental sync adds GitHub deltas for
``[last_sync_at + 1s, now]`` on top of totals that may already include that window — expect double
counting unless you delete the row for a fresh ``first_sync`` or manually realign counters.

Usage (from repo root, stack up)::

    docker compose run --rm api sh -lc \\
      "cd /app && pip install -q '.[dev]' \\
      && PYTHONPATH=/app python scripts/repl_db_example.py LOGIN --hours-ago 7"

Or from ``task shell`` (``#`` prompt, PYTHONPATH already exported)::

    python scripts/repl_db_example.py LOGIN --hours-ago 7

``github_login`` must match the stored value exactly (case-sensitive). Use ``exit()`` if you see a
``>>>`` Python prompt; use ``task shell:python`` only for an interactive REPL.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from app.database import AsyncSessionLocal
from app.models.developer import Developer
from sqlalchemy import select


async def set_last_sync_hours_ago(github_login: str, hours_ago: float) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(Developer.github_login == github_login),
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            raise SystemExit(f"No developer with github_login={github_login!r}")
        dev.last_sync_at = datetime.now(tz=UTC) - timedelta(hours=hours_ago)
        await session.commit()
        print(f"{dev.id} {dev.github_login!r} last_sync_at={dev.last_sync_at.isoformat()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("github_login", help="Exact github_login column value in DB")
    parser.add_argument(
        "--hours-ago",
        type=float,
        default=7.0,
        help="Set last_sync_at to UTC now minus this many hours (default 7 clears 6h cooldown)",
    )
    args = parser.parse_args()
    asyncio.run(set_last_sync_hours_ago(args.github_login, args.hours_ago))


if __name__ == "__main__":
    main()
