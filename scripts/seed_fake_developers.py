#!/usr/bin/env python3
"""Seed the DB with fake developers for planet rendering tests.

Generates developers with a realistic XP distribution (log-normal):
lots of juniors, some mid-level, a handful of whales.
All islands are covered proportionally.

Usage (from repo root, stack up)::

    docker compose run --rm api sh -lc \
      "cd /app && PYTHONPATH=/app python scripts/seed_fake_developers.py"

Or from ``task shell``::

    python scripts/seed_fake_developers.py --count 1000
    python scripts/seed_fake_developers.py --count 500 --clear

Options:
  --count N   Number of fake developers to insert (default: 500)
  --clear     Delete all existing fake developers before inserting
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.database import AsyncSessionLocal
from app.domain.island import IslandChoice
from app.domain.scoring import get_cell_count, get_level, get_player_class
from app.models.developer import Developer
from app.workers.planet_task import update_planet_json

FAKE_LOGIN_PREFIX = "fake_dev_"

FAKE_GITHUB_ID_BASE = 900_000_000

ISLANDS = [i.value for i in IslandChoice]

ISLAND_WEIGHTS = {
    "frontend":     18,
    "fullstack":    16,
    "backend":      15,
    "ai":           13,
    "indie_hacker": 10,
    "data":          9,
    "infra":         8,
    "open_source":   6,
    "mobile":        4,
    "vibe_coding":   1,
}


def _sample_xp(rng: random.Random) -> int:
    """Log-normal distribution tuned to match realistic GitHub XP spread.

    Roughly:
      - 50 % of devs: XP < 3 000   (Seedling / Builder)
      - 30 % of devs: XP 3–20 000  (Crafter / Architect)
      - 15 % of devs: XP 20–115 000 (Maintainer)
      -  5 % of devs: XP > 115 000  (Legend / Sovereign / Founder)
    """
    raw = rng.lognormvariate(mu=7.5, sigma=1.6)
    return max(0, min(int(raw), 1_400_000))


def _make_fake_developer(index: int, rng: random.Random, now: datetime) -> dict[str, object]:
    xp = _sample_xp(rng)
    island = rng.choices(ISLANDS, weights=[ISLAND_WEIGHTS[i] for i in ISLANDS], k=1)[0]
    account_age_days = rng.randint(180, 4000)

    return {
        "id": uuid.uuid4(),
        "github_id": FAKE_GITHUB_ID_BASE + index,
        "github_login": f"{FAKE_LOGIN_PREFIX}{index:06d}",
        "commits_alltime": rng.randint(0, int(xp / 10) + 1),
        "prs_contributions_alltime": rng.randint(0, int(xp / 50) + 1),
        "reviews_alltime": rng.randint(0, int(xp / 30) + 1),
        "forks_received": rng.randint(0, 50),
        "followers": rng.randint(0, 200),
        "stars_received_raw": rng.randint(0, 500),
        "stars_received_capped": rng.randint(0, 300),
        "owned_non_fork_repos_count": rng.randint(1, 30),
        "account_created_at": now - timedelta(days=account_age_days),
        "xp_brut": xp,
        "last_sync_at": now - timedelta(hours=rng.randint(1, 720)),
        "island": island,
        "is_onboarded": True,
        "created_at": now,
        "updated_at": now,
    }


async def clear_fake_developers(session) -> int:
    result = await session.execute(
        delete(Developer).where(Developer.github_login.like(f"{FAKE_LOGIN_PREFIX}%"))
    )
    return result.rowcount


async def seed(count: int, clear: bool) -> None:
    rng = random.Random(42)  # deterministic seed for reproducibility
    now = datetime.now(tz=UTC)

    async with AsyncSessionLocal() as session:
        if clear:
            deleted = await clear_fake_developers(session)
            await session.commit()
            print(f"🗑  Deleted {deleted} existing fake developers.")

        # Find the highest existing fake index to avoid collisions on re-runs.
        result = await session.execute(
            select(Developer.github_id)
            .where(Developer.github_id >= FAKE_GITHUB_ID_BASE)
            .order_by(Developer.github_id.desc())
            .limit(1)
        )
        last_id = result.scalar_one_or_none()
        start_index = (last_id - FAKE_GITHUB_ID_BASE + 1) if last_id is not None else 0

        rows = [_make_fake_developer(start_index + i, rng, now) for i in range(count)]

        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            stmt = insert(Developer).values(batch).on_conflict_do_nothing(index_elements=["github_id"])
            await session.execute(stmt)
            await session.commit()
            print(f"  .. inserted batch {i//batch_size + 1}/{math.ceil(len(rows)/batch_size)}")

    # Print a quick summary.
    xps = [r["xp_brut"] for r in rows]  # type: ignore[index]
    levels = [get_level(x) for x in xps]  # type: ignore[arg-type]
    cells = [get_cell_count(x) for x in xps]  # type: ignore[arg-type]
    classes = [get_player_class(lv).name for lv in levels]

    island_counts: dict[str, int] = {}
    for r in rows:
        island_counts[r["island"]] = island_counts.get(r["island"], 0) + 1  # type: ignore[index]

    print(f"\n✅ Inserted {count} fake developers (starting at index {start_index})\n")
    print("XP distribution:")
    buckets = [(0, 1_000), (1_000, 6_300), (6_300, 22_000), (22_000, 115_000), (115_000, math.inf)]
    labels  = ["< 1k (Seedling)", "1k–6k (Builder)", "6k–22k (Crafter)", "22k–115k (Architect+)", "> 115k (Legend+)"]
    for (lo, hi), label in zip(buckets, labels, strict=True):
        n = sum(1 for x in xps if lo <= x < hi)  # type: ignore[operator]
        bar = "█" * int(n / count * 40)
        print(f"  {label:<28} {n:4d}  {bar}")

    print("\nIsland distribution:")
    for island, n in sorted(island_counts.items(), key=lambda x: -x[1]):
        bar = "█" * int(n / count * 30)
        print(f"  {island:<16} {n:4d}  {bar}")

    print(f"\nCells  — min: {min(cells)}, avg: {sum(cells)//count}, max: {max(cells)}")
    print(f"Levels — min: {min(levels)}, avg: {sum(levels)//count}, max: {max(levels)}")
    print(f"Classes: { {c: classes.count(c) for c in sorted(set(classes))} }")

    update_planet_json.delay()
    print("Planet JSON updated successfully.")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=500, help="Number of fake developers to insert")
    parser.add_argument("--clear", action="store_true", help="Delete existing fake developers first")
    args = parser.parse_args()
    asyncio.run(seed(args.count, args.clear))


if __name__ == "__main__":
    main()
