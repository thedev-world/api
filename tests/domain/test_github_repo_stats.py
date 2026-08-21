from app.domain.github_repo_stats import merge_repo_stats, repo_stats_from_pages


def test_repo_stats_from_pages_skips_forks() -> None:
    pages = [
        [
            {"full_name": "alice/app", "stargazers_count": 10, "forks_count": 2, "fork": False},
            {"full_name": "alice/forked", "stargazers_count": 999, "forks_count": 1, "fork": True},
        ]
    ]
    assert repo_stats_from_pages(pages) == {"alice/app": (10, 2)}


def test_merge_repo_stats_deduplicates_by_full_name() -> None:
    personal = {"alice/app": (7, 1)}
    org = {"ferriskey/ferriskey": (682, 40), "alice/app": (100, 0)}
    stars, forks = merge_repo_stats(personal, org)
    assert stars == (7, 682)
    assert forks == 41


def test_merge_repo_stats_empty_sources() -> None:
    assert merge_repo_stats({}) == ((), 0)
    assert merge_repo_stats({}, {}) == ((), 0)
