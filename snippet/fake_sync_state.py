#!/usr/bin/env python3
"""Fake sync state to trigger XP reveal animation with a specific before/after scenario.

Manipulates ``xp_brut``, raw stats, and ``last_sync_at`` so the next POST /me/sync
produces a predictable XP diff that triggers the reveal animation.

Strategy
--------
The incremental sync **adds** the GitHub delta to stored stats and recalculates XP.
By adjusting ``commits_alltime`` (10 XP each) we can target any desired post-sync XP,
assuming the GitHub delta during the cooldown window is ~0 (true for most users who
haven't pushed in the past few hours).

Usage (from repo root, stack up)::

    docker compose run --rm api sh -lc \\
      "cd /app && pip install -q '.[dev]' \\
      && PYTHONPATH=/app python snippet/fake_sync_state.py GITHUB_LOGIN"

Or from ``task shell`` (``#`` prompt, PYTHONPATH already exported)::

    # Default: subtract 500 XP from current, last_sync 12h ago
    python snippet/fake_sync_state.py GITHUB_LOGIN

    # Custom delta (XP bar fill, same level)
    python snippet/fake_sync_state.py GITHUB_LOGIN --xp-delta 2000

    # Full level-up scenario: set before=54000, after=56000 (crosses lvl-33 at ~55100)
    python snippet/fake_sync_state.py GITHUB_LOGIN --xp-before 54000 --xp-after 56000

    # See available level thresholds
    python snippet/fake_sync_state.py --list-levels

Arguments:
  GITHUB_LOGIN   Exact github_login column value in DB (case-sensitive).

Options:
  --xp-before N   Set xp_brut (and adjust raw stats) to produce exactly N XP before
                  the next sync. Defaults to current_xp - xp_delta.
  --xp-after N    Boost commits_alltime so the next sync recalculates to ≈N XP.
                  Defaults to current real XP (no boost).
  --xp-delta N    Shorthand: xp-before = current_xp - N, xp-after = current_xp.
                  Default: 500. Ignored when --xp-before/--xp-after are provided.
  --hours-ago N   Set last_sync_at to N hours ago (default: 12, must be > 6).
  --list-levels   Print level thresholds and exit.
"""

from __future__ import annotations

import argparse
import asyncio
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.domain.datetime_github import github_account_age_full_years
from app.domain.scoring import PLAYER_CLASSES_LIST, get_level, get_xp_progress
from app.models.developer import Developer


# ---------------------------------------------------------------------------
# XP helpers
# ---------------------------------------------------------------------------

def _xp_for_level(level: int) -> int:
    return round(100 * math.pow(level, 1.8))


def _xp_from_stats(
    *,
    commits: int,
    prs: int,
    reviews: int,
    stars_capped: int,
    forks: int,
    followers: int,
    years: int,
) -> int:
    followers_capped = min(followers, 500)
    return (
        commits * 10
        + prs * 30
        + reviews * 15
        + stars_capped * 50
        + forks * 40
        + followers_capped * 20
        + years * 200
    )


def _commits_for_xp_target(
    target_xp: int,
    *,
    prs: int,
    reviews: int,
    stars_capped: int,
    forks: int,
    followers: int,
    years: int,
) -> int:
    """Return commits_alltime required to produce target_xp (clamped to ≥0)."""
    followers_capped = min(followers, 500)
    rest = (
        prs * 30
        + reviews * 15
        + stars_capped * 50
        + forks * 40
        + followers_capped * 20
        + years * 200
    )
    return max(0, math.ceil((target_xp - rest) / 10))


def _list_levels() -> None:
    print("Level thresholds (first 50 levels + player class tiers):\n")
    class_map = {c.required_level: c.name for c in PLAYER_CLASSES_LIST}
    for lvl in range(1, 51):
        xp = _xp_for_level(lvl) if lvl > 1 else 0
        cls = class_map.get(lvl, "")
        tag = f"  ← {cls}" if cls else ""
        print(f"  Level {lvl:>3}  {xp:>8} XP{tag}")


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

async def fake_sync_state(
    github_login: str,
    *,
    xp_before: int | None,
    xp_after: int | None,
    xp_delta: int,
    hours_ago: int,
) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(Developer.github_login == github_login),
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            raise SystemExit(f"No developer with github_login={github_login!r}")

        years = github_account_age_full_years(dev.account_created_at)
        real_xp = dev.xp_brut

        # Resolve before/after targets
        target_before = xp_before if xp_before is not None else max(0, real_xp - xp_delta)
        target_after = xp_after if xp_after is not None else real_xp

        if target_after <= target_before:
            raise SystemExit(
                f"xp-after ({target_after}) must be greater than xp-before ({target_before})."
            )

        # Adjust commits_alltime to produce target_before XP from stored stats
        commits_for_before = _commits_for_xp_target(
            target_before,
            prs=dev.prs_contributions_alltime,
            reviews=dev.reviews_alltime,
            stars_capped=dev.stars_received_capped,
            forks=dev.forks_received,
            followers=dev.followers,
            years=years,
        )
        actual_before_xp = _xp_from_stats(
            commits=commits_for_before,
            prs=dev.prs_contributions_alltime,
            reviews=dev.reviews_alltime,
            stars_capped=dev.stars_received_capped,
            forks=dev.forks_received,
            followers=dev.followers,
            years=years,
        )

        # Adjust commits_alltime to produce target_after XP (the sync will read these)
        commits_for_after = _commits_for_xp_target(
            target_after,
            prs=dev.prs_contributions_alltime,
            reviews=dev.reviews_alltime,
            stars_capped=dev.stars_received_capped,
            forks=dev.forks_received,
            followers=dev.followers,
            years=years,
        )

        fake_last_sync = datetime.now(tz=UTC) - timedelta(hours=hours_ago)

        # Store the "before" XP and the stats that will produce "after" XP when recalculated
        # The sync will: prev_snap = snapshot_from_row (reads xp_brut=before),
        # then recalculates from fetched GitHub stats. We boost commits_alltime so
        # the incremental path ends at ~target_after (assuming 0 GitHub delta).
        dev.xp_brut = actual_before_xp
        dev.commits_alltime = commits_for_after  # recalculated by sync → produces target_after
        dev.last_sync_at = fake_last_sync
        dev.updated_at = datetime.now(tz=UTC)

        await session.commit()

        prog_before = get_xp_progress(actual_before_xp)
        prog_after = get_xp_progress(target_after)

        print(
            f"✓ {dev.github_login!r} (id={dev.id})\n"
            f"\n  XP before    : {actual_before_xp:>8}  →  level {prog_before.level}  "
            f"({prog_before.xp_in_level}/{prog_before.xp_needed} xp, {prog_before.percent}%)\n"
            f"  XP after     : {target_after:>8}  →  level {prog_after.level}  "
            f"({prog_after.xp_in_level}/{prog_after.xp_needed} xp, {prog_after.percent}%)\n"
            f"  Diff         : +{target_after - actual_before_xp}\n"
            f"  Level change : {prog_before.level} → {prog_after.level} "
            f"{'🎉' if prog_after.level > prog_before.level else '(same level)'}\n"
            f"\n  commits_alltime set to {commits_for_after} (was {dev.commits_alltime})"
            f" to produce ~{target_after} XP on re-sync\n"
            f"  last_sync_at : {fake_last_sync.isoformat()}  ({hours_ago}h ago)\n"
            f"\nNext POST /me/sync will produce the diff above and trigger the reveal animation.\n"
            f"⚠  If you have real GitHub activity in the last {hours_ago}h, xp_after may be slightly higher."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "github_login", nargs="?", help="Exact github_login column value in DB"
    )
    parser.add_argument(
        "--xp-before", type=int, default=None, metavar="N",
        help="Target XP to store as xp_brut before next sync",
    )
    parser.add_argument(
        "--xp-after", type=int, default=None, metavar="N",
        help="Target XP the next sync should produce (~assumes 0 GitHub delta)",
    )
    parser.add_argument(
        "--xp-delta", type=int, default=500, metavar="N",
        help="Shorthand: xp-before = current_xp - N  (default: 500). Ignored if --xp-before is set.",
    )
    parser.add_argument(
        "--hours-ago", type=int, default=12, metavar="N",
        help="Set last_sync_at N hours ago (default: 12, must be > 6 to bypass cooldown)",
    )
    parser.add_argument(
        "--list-levels", action="store_true",
        help="Print level thresholds and exit",
    )
    args = parser.parse_args()

    if args.list_levels:
        _list_levels()
        return

    if not args.github_login:
        parser.error("github_login is required unless --list-levels is used")

    if args.hours_ago <= 6:
        print(f"⚠ Warning: --hours-ago={args.hours_ago} ≤ 6h cooldown. Sync may be skipped.")

    asyncio.run(
        fake_sync_state(
            args.github_login,
            xp_before=args.xp_before,
            xp_after=args.xp_after,
            xp_delta=args.xp_delta,
            hours_ago=args.hours_ago,
        )
    )


if __name__ == "__main__":
    main()

