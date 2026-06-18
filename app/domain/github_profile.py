from __future__ import annotations

from typing import Any

from app.models.developer import Developer


def github_profile_avatar_url(profile: dict[str, Any]) -> str | None:
    raw = profile.get("avatar_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def sync_avatar_url_from_profile(developer: Developer, profile: dict[str, Any]) -> bool:
    """Store GitHub avatar URL when missing or changed."""
    source = github_profile_avatar_url(profile)
    if source is None or developer.avatar_url == source:
        return False
    developer.avatar_url = source
    return True
