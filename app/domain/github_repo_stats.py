from __future__ import annotations

from typing import Any

RepoStats = dict[str, tuple[int, int]]


def repo_stats_from_pages(pages: list[list[dict[str, Any]]]) -> RepoStats:
    """Build full_name -> (stars, forks) from GitHub REST repo list pages."""
    stats: RepoStats = {}
    for batch in pages:
        for repo in batch:
            if not isinstance(repo, dict):
                continue
            if repo.get("fork"):
                continue
            full_name = repo.get("full_name")
            if not isinstance(full_name, str) or not full_name.strip():
                continue
            stars = int(repo.get("stargazers_count", 0) or 0)
            forks = int(repo.get("forks_count", 0) or 0)
            stats[full_name] = (stars, forks)
    return stats


def merge_repo_stats(*sources: RepoStats) -> tuple[tuple[int, ...], int]:
    """Merge repo stats without double-counting the same full_name."""
    merged: RepoStats = {}
    for source in sources:
        for full_name, counts in source.items():
            if full_name not in merged:
                merged[full_name] = counts
    stars_per_repo = tuple(stars for stars, _ in merged.values())
    forks_received = sum(forks for _, forks in merged.values())
    return stars_per_repo, forks_received
