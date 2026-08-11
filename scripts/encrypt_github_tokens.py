#!/usr/bin/env python3
"""Encrypt plaintext developers.github_token values before serving encrypted reads.

Run after `alembic upgrade head` with TOKEN_ENCRYPTION_KEY set. Safe to re-run:
already encrypted rows are skipped.

Usage (from repo root, stack up):

    docker compose run --rm api sh -lc \\
      "cd /app && PYTHONPATH=/app python scripts/encrypt_github_tokens.py"

Or:

    task tokens:encrypt
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.token_encryption import ensure_token_encrypted
from app.database import AsyncSessionLocal


async def encrypt_github_tokens(*, dry_run: bool) -> tuple[int, int]:
    encrypted = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT id, github_token FROM developers WHERE github_token IS NOT NULL"),
        )
        rows = result.all()

        for developer_id, raw_token in rows:
            if not isinstance(raw_token, str) or not raw_token:
                continue

            stored = ensure_token_encrypted(raw_token)
            if stored == raw_token:
                skipped += 1
                continue

            encrypted += 1
            if dry_run:
                continue

            await session.execute(
                text("UPDATE developers SET github_token = :token WHERE id = :id"),
                {"token": stored, "id": developer_id},
            )

        if not dry_run:
            await session.commit()

    return encrypted, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many rows would change without writing",
    )
    args = parser.parse_args()

    encrypted, skipped = await encrypt_github_tokens(dry_run=args.dry_run)
    mode = "Would encrypt" if args.dry_run else "Encrypted"
    print(f"{mode} {encrypted} token(s), skipped {skipped} already encrypted.")


if __name__ == "__main__":
    asyncio.run(main())
