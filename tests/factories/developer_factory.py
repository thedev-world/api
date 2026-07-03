"""Test builders — not persisted."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.developer import Developer

_FIXED_ID = uuid.UUID("aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee")
_ANCHOR = datetime(2020, 6, 15, tzinfo=UTC)


def make_developer(**overrides: object) -> Developer:
    """ORM instance not attached to a session (fine for mocking row state)."""
    defaults: dict[str, object] = {
        "id": _FIXED_ID,
        "github_id": 424242,
        "github_login": "testdev",
        "github_token": None,
        "commits_alltime": 0,
        "prs_contributions_alltime": 0,
        "reviews_alltime": 0,
        "forks_received": 0,
        "followers": 0,
        "stars_received_raw": 0,
        "stars_received_capped": 0,
        "owned_non_fork_repos_count": 0,
        "account_created_at": _ANCHOR,
        "xp_brut": 0,
        "last_sync_at": _ANCHOR,
        "island": None,
        "is_onboarded": False,
        "avatar_url": None,
        "created_at": _ANCHOR,
        "updated_at": _ANCHOR,
    }
    merged = {**defaults, **overrides}
    return Developer(**merged)
