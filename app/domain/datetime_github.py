"""GitHub-aligned datetime helpers kept free of HTTP client imports."""

from __future__ import annotations

from datetime import UTC, datetime


def github_account_age_full_years(created_at: datetime) -> int:
    """Full calendar years approximation (365-day buckets) from account creation."""
    now = datetime.now(tz=UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.astimezone(UTC)
    if created_at > now:
        return 0
    years = (now - created_at).days // 365
    return max(0, int(years))


def parse_github_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
