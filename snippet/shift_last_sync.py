#!/usr/bin/env python3
"""Move ``Developer.last_sync_at`` into the past so the next POST /me/sync can run.

Usage (from repo root, stack up)::

    docker compose run --rm api sh -lc \\
      "cd /app && PYTHONPATH=/app python snippet/shift_last_sync.py GITHUB_LOGIN"

Or from ``task shell``::

    python snippet/shift_last_sync.py GITHUB_LOGIN
    python snippet/shift_last_sync.py GITHUB_LOGIN --days-ago 1
    python snippet/shift_last_sync.py GITHUB_LOGIN --full   # last_sync_at = NULL → full backfill

Incremental sync only counts GitHub activity **since last_sync_at**.
Use ``--full`` after making a private repo public if you want all-time public
commits picked up, not just the last N days.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.developer import Developer


async def shift_last_sync(
    github_login: str,
    *,
    days_ago: int,
    full_backfill: bool,
) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(Developer.github_login == github_login),
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            raise SystemExit(f"No developer with github_login={github_login!r}")

        previous = dev.last_sync_at
        now = datetime.now(tz=UTC)

        if full_backfill:
            dev.last_sync_at = None
            dev.updated_at = now
            await session.commit()
            print(
                f"✓ {dev.github_login!r} (id={dev.id})\n"
                f"  last_sync_at: {previous!r} → NULL\n"
                f"  Next sync will full-backfill from GitHub (all-time public activity)."
            )
            return

        target = now - timedelta(days=days_ago)
        dev.last_sync_at = target
        dev.updated_at = now
        await session.commit()

        print(
            f"✓ {dev.github_login!r} (id={dev.id})\n"
            f"  last_sync_at: {previous!r}\n"
            f"           →   {target.isoformat()}\n"
            f"  Next sync will add GitHub delta from that timestamp (incremental only)."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("github_login", help="Exact github_login column value in DB")
    parser.add_argument(
        "--days-ago",
        type=int,
        default=1,
        metavar="N",
        help="Set last_sync_at to N days ago (default: 1 = yesterday)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Clear last_sync_at so next sync re-imports all public stats from scratch",
    )
    args = parser.parse_args()

    if args.days_ago < 1 and not args.full:
        raise SystemExit("--days-ago must be >= 1")

    asyncio.run(
        shift_last_sync(
            args.github_login,
            days_ago=args.days_ago,
            full_backfill=args.full,
        )
    )


if __name__ == "__main__":
    main()
