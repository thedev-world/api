#!/usr/bin/env python3
"""Re-sync a developer from GitHub and refresh planet-data.json on S3.

Bypasses the 6h POST /me/sync cooldown (admin/maintenance use).

Usage (local stack)::

    docker compose exec api /venv/bin/python snippet/sync_github_user.py GITHUB_LOGIN

    docker compose exec api /venv/bin/python snippet/sync_github_user.py GITHUB_LOGIN --capture

Prod (API container, env from deploy)::

    docker compose exec api /venv/bin/python \
    /app/snippet/sync_github_user.py GITHUB_LOGIN

Options:
  --full       Clear last_sync_at before sync (first-sync code path; same all-time
               GitHub refresh for commits/PRs/reviews on current code)
  --skip-s3    Update DB only, do not upload planet-data.json
  --capture    Also enqueue profile JPEG capture (Celery capture queue)
  --dry-run    Fetch GitHub stats and print before/after diff without DB or S3 writes
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.clients.github import GitHubClient
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.domain.scoring import calculate_xp, get_cell_count
from app.models.developer import Developer
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService
from app.workers.celery_app import celery
from app.workers.planet_task import update_planet_json

SYNC_COOLDOWN = timedelta(hours=6)


def _format_stats(commits: int, prs: int, reviews: int, xp: int) -> str:
    cells = get_cell_count(xp)
    return f"commits={commits} prs={prs} reviews={reviews} xp={xp} cells={cells}"


async def _preview_after_sync(dev: Developer) -> tuple[int, int, int, int, int]:
    settings = get_settings()
    github = GitHubClient(settings).with_token(dev.github_token)
    inputs = await github.fetch_score_inputs(dev.github_login)
    xp, _ = calculate_xp(inputs)
    cells = get_cell_count(xp)
    return (
        inputs.commits_alltime,
        inputs.prs_contributions_alltime,
        inputs.reviews_alltime,
        xp,
        cells,
    )

async def sync_user(
    github_login: str,
    *,
    full_backfill: bool,
    dry_run: bool,
) -> Developer | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(func.lower(Developer.github_login) == github_login.lower()),
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            return None

        login = dev.github_login
        before_commits = dev.commits_alltime
        before_prs = dev.prs_contributions_alltime
        before_reviews = dev.reviews_alltime
        before_xp = dev.xp_brut
        before_cells = get_cell_count(before_xp)

        print(
            f"Found {login!r} (id={dev.id}, github_id={dev.github_id})\n"
            f"  before: {_format_stats(before_commits, before_prs, before_reviews, before_xp)} "
            f"last_sync_at={dev.last_sync_at!r}\n"
            f"  has_oauth_token={bool(dev.github_token)} onboarded={dev.is_onboarded}"
        )

        if dry_run:
            action = "full backfill" if full_backfill else "incremental refresh"
            if not dev.github_token:
                print("  warning: no OAuth token stored — preview uses server token (may be inaccurate)")
            after_commits, after_prs, after_reviews, after_xp, after_cells = await _preview_after_sync(
                dev
            )
            print(f"  after:  {_format_stats(after_commits, after_prs, after_reviews, after_xp)}")
            print(
                f"  delta:  commits={after_commits - before_commits:+d} "
                f"prs={after_prs - before_prs:+d} "
                f"reviews={after_reviews - before_reviews:+d} "
                f"xp={after_xp - before_xp:+d} "
                f"cells={after_cells - before_cells:+d}"
            )
            print(f"  dry-run: would run {action}, persist to DB, and upload planet-data.json to S3")
            return dev

        now = datetime.now(tz=UTC)
        if full_backfill:
            dev.last_sync_at = None
        elif dev.last_sync_at is not None:
            last = dev.last_sync_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            last = last.astimezone(UTC)
            if now - last < SYNC_COOLDOWN:
                dev.last_sync_at = now - SYNC_COOLDOWN - timedelta(minutes=1)
                print(f"  bypassing cooldown (last_sync_at → {dev.last_sync_at.isoformat()})")

        dev.updated_at = now
        await session.commit()

    settings = get_settings()
    service = ScoreSyncService(GitHubClient(settings))

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(func.lower(Developer.github_login) == github_login.lower()),
        )
        dev = result.scalar_one()
        outcome = await service.sync_for_actor(
            session,
            github_id=dev.github_id,
            login=dev.github_login,
        )

        if isinstance(outcome, MeSyncCooldown):
            raise RuntimeError(
                f"Sync still blocked by cooldown (retry_after={outcome.retry_after.isoformat()})"
            )

        assert isinstance(outcome, MeSyncPerformed)
        await session.refresh(dev)

        print(
            f"  after:  {_format_stats(dev.commits_alltime, dev.prs_contributions_alltime, dev.reviews_alltime, dev.xp_brut)}\n"
            f"  sync: first_sync={outcome.first_sync}"
        )
        if outcome.progress is not None:
            p = outcome.progress
            print(
                f"  progress: xp {p.xp_before} → {p.xp_after}, "
                f"cells {p.cell_before} → {p.cell_after}"
            )
        return dev


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("github_login", help="GitHub login (case-insensitive)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Clear last_sync_at before sync (first-sync branch)",
    )
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Skip planet-data.json upload",
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Enqueue profile capture task after sync",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch GitHub and print before/after diff without DB or S3 writes",
    )
    args = parser.parse_args()

    login = args.github_login.strip()
    if not login:
        raise SystemExit("GitHub login cannot be empty")

    try:
        dev = asyncio.run(
            sync_user(login, full_backfill=args.full, dry_run=args.dry_run),
        )
    except Exception as exc:
        raise SystemExit(f"Sync failed: {exc}") from exc

    if dev is None:
        raise SystemExit(f"No developer with github_login matching {login!r}")

    if args.dry_run or args.skip_s3:
        if args.skip_s3 and not args.dry_run:
            print("Skipping S3 upload (--skip-s3)")
        return

    print("Uploading planet-data.json to S3...")
    try:
        update_planet_json()
        print("S3 upload completed.")
    except Exception as exc:
        raise SystemExit(
            f"S3 upload failed: {exc}\nNote: DB was updated; planet-data.json may be stale."
        ) from exc

    if args.capture:
        print(f"Enqueueing profile capture for {dev.github_login!r}...")
        celery.send_task(
            "devplanet.workers.generate_profile_capture",
            args=[dev.github_login],
            queue="capture",
        )
        print("Capture task enqueued.")


if __name__ == "__main__":
    main()
