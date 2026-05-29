#!/usr/bin/env python3
"""Set ``Developer.is_onboarded`` to ``False`` for a given user.

Usage (from repo root, stack up)::

    docker compose run --rm api sh -lc \\
      "cd /app && pip install -q '.[dev]' \\
      && PYTHONPATH=/app python snippet/reset_onboarding.py GITHUB_LOGIN"

Or from ``task shell`` (``#`` prompt, PYTHONPATH already exported)::

    python snippet/reset_onboarding.py GITHUB_LOGIN

``github_login`` must match the stored value exactly (case-sensitive).
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.developer import Developer


async def reset_onboarding(github_login: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Developer).where(Developer.github_login == github_login),
        )
        dev = result.scalar_one_or_none()
        if dev is None:
            raise SystemExit(f"No developer with github_login={github_login!r}")
        dev.is_onboarded = False
        await session.commit()
        print(f"✓ {dev.github_login!r} (id={dev.id}) → is_onboarded=False")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("github_login", help="Exact github_login column value in DB")
    args = parser.parse_args()
    asyncio.run(reset_onboarding(args.github_login))


if __name__ == "__main__":
    main()
