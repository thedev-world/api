#!/usr/bin/env python3
"""Re-sync all developers from GitHub and refresh planet-data.json on S3.

Bypasses the 6h POST /me/sync cooldown for every row (admin/maintenance use).

Usage (local stack)::

    docker compose exec api /venv/bin/python snippet/resync_all_users.py --dry-run
    docker compose exec api /venv/bin/python snippet/resync_all_users.py
    docker compose exec api /venv/bin/python snippet/resync_all_users.py --skip-s3

Prod (API container)::

    docker compose exec api /venv/bin/python /app/snippet/resync_all_users.py --dry-run
    docker compose exec api /venv/bin/python /app/snippet/resync_all_users.py

Options:
  --dry-run       List developers and exit without DB or S3 writes
  --skip-s3       Update DB only, do not upload planet-data.json
  --sleep SECS    Pause between each user sync (default: 1.0, GitHub rate limits)
  --limit N       Sync at most N developers (useful for testing)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.clients.github import GitHubClient
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.developer import Developer
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService
from app.workers.planet_task import update_planet_json

SYNC_COOLDOWN = timedelta(hours=6)


async def _fetch_all_developers() -> list[Developer]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Developer).order_by(Developer.github_login))
        return list(result.scalars().all())


async def _bypass_cooldown_for_all() -> None:
    now = datetime.now(tz=UTC)
    bypass_at = now - SYNC_COOLDOWN - timedelta(minutes=1)
    async with AsyncSessionLocal() as session:
        devs = (await session.execute(select(Developer))).scalars().all()
        for dev in devs:
            dev.last_sync_at = bypass_at
            dev.updated_at = now
        await session.commit()


async def resync_all(
    *,
    dry_run: bool,
    sleep_seconds: float,
    limit: int | None,
) -> tuple[int, int, int]:
    devs = await _fetch_all_developers()
    if limit is not None:
        devs = devs[:limit]

    print(f"Found {len(devs)} developer(s)")
    for dev in devs:
        token = "yes" if dev.github_token else "no"
        print(
            f"  - {dev.github_login!r}  "
            f"commits={dev.commits_alltime}  private={dev.private_contributions_alltime}  "
            f"oauth_token={token}"
        )

    if dry_run:
        print("\nDry-run: no DB or S3 changes.")
        return (0, 0, 0)

    await _bypass_cooldown_for_all()

    settings = get_settings()
    service = ScoreSyncService(GitHubClient(settings))

    ok = skip = err = 0
    for dev in devs:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(select(Developer).where(Developer.id == dev.id))
            ).scalar_one()
            try:
                outcome = await service.sync_for_actor(
                    session,
                    github_id=row.github_id,
                    login=row.github_login,
                )
                if isinstance(outcome, MeSyncPerformed):
                    ok += 1
                    print(
                        f"OK  {row.github_login!r}  "
                        f"commits={row.commits_alltime}  "
                        f"private={row.private_contributions_alltime}  "
                        f"xp={row.xp_brut}"
                    )
                elif isinstance(outcome, MeSyncCooldown):
                    skip += 1
                    print(f"SKIP {row.github_login!r}  cooldown until {outcome.retry_after.isoformat()}")
                else:
                    skip += 1
                    print(f"SKIP {row.github_login!r}  unexpected outcome: {outcome!r}")
            except Exception as exc:
                err += 1
                print(f"ERR {row.github_login!r}: {exc}")

        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

    return (ok, skip, err)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="List developers without syncing")
    parser.add_argument("--skip-s3", action="store_true", help="Skip planet-data.json upload")
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        metavar="SECS",
        help="Pause between each sync (default: 1.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Sync at most N developers",
    )
    args = parser.parse_args()

    if args.sleep < 0:
        raise SystemExit("--sleep must be >= 0")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be >= 1")

    try:
        ok, skip, err = asyncio.run(
            resync_all(
                dry_run=args.dry_run,
                sleep_seconds=args.sleep,
                limit=args.limit,
            )
        )
    except Exception as exc:
        raise SystemExit(f"Resync failed: {exc}") from exc

    if args.dry_run:
        return

    print(f"\nDone: ok={ok} skip={skip} err={err}")

    if args.skip_s3:
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


if __name__ == "__main__":
    main()
