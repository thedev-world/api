from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.clients.github import GitHubAPIError, GitHubClient, GitHubUserNotFoundError


def _make_client() -> GitHubClient:
    settings = MagicMock()
    settings.github_api_base = "https://api.github.com"
    settings.github_token = None
    return GitHubClient(settings)


def _patch_totals_for_range(return_values: list[tuple[int, int, int]]) -> MagicMock:
    return AsyncMock(side_effect=return_values)


@pytest.mark.asyncio
async def test_contributions_totals_between_within_one_year() -> None:
    client = _make_client()
    range_from = datetime(2026, 1, 15, tzinfo=UTC)
    range_to = datetime(2026, 5, 5, tzinfo=UTC)

    mock_inner = _patch_totals_for_range([(7, 3, 1)])
    with patch.object(client, "_contribution_totals_for_range", new=mock_inner):
        result = await client.contributions_totals_between("alice", range_from, range_to)

    assert result == (7, 3, 1)
    mock_inner.assert_awaited_once()
    _, args, _ = mock_inner.mock_calls[0]
    assert args[2] == range_from
    assert args[3] == range_to


@pytest.mark.asyncio
async def test_contributions_totals_between_crossing_year_boundary() -> None:
    client = _make_client()
    range_from = datetime(2025, 12, 20, tzinfo=UTC)
    range_to = datetime(2026, 5, 5, tzinfo=UTC)

    mock_inner = _patch_totals_for_range([(5, 2, 0), (10, 4, 1)])
    with patch.object(client, "_contribution_totals_for_range", new=mock_inner):
        result = await client.contributions_totals_between("alice", range_from, range_to)

    assert result == (15, 6, 1)
    assert mock_inner.await_count == 2

    calls = mock_inner.mock_calls
    _, args_2025, _ = calls[0]
    assert args_2025[2] == range_from
    assert args_2025[3] == datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
    _, args_2026, _ = calls[1]
    assert args_2026[2] == datetime(2026, 1, 1, tzinfo=UTC)
    assert args_2026[3] == range_to


@pytest.mark.asyncio
async def test_contributions_totals_between_spanning_more_than_one_year() -> None:
    client = _make_client()
    range_from = datetime(2024, 6, 1, tzinfo=UTC)
    range_to = datetime(2026, 5, 5, tzinfo=UTC)

    mock_inner = _patch_totals_for_range([(20, 5, 2), (50, 10, 4), (8, 3, 1)])
    with patch.object(client, "_contribution_totals_for_range", new=mock_inner):
        result = await client.contributions_totals_between("alice", range_from, range_to)

    assert result == (78, 18, 7)
    assert mock_inner.await_count == 3

    calls = mock_inner.mock_calls
    _, args_2024, _ = calls[0]
    assert args_2024[2] == range_from
    assert args_2024[3] == datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)

    _, args_2025, _ = calls[1]
    assert args_2025[2] == datetime(2025, 1, 1, tzinfo=UTC)
    assert args_2025[3] == datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

    _, args_2026, _ = calls[2]
    assert args_2026[2] == datetime(2026, 1, 1, tzinfo=UTC)
    assert args_2026[3] == range_to


@pytest.mark.asyncio
async def test_contributions_totals_between_range_from_after_range_to_returns_zeros() -> None:
    client = _make_client()
    mock_inner = AsyncMock()
    with patch.object(client, "_contribution_totals_for_range", new=mock_inner):
        result = await client.contributions_totals_between(
            "alice",
            datetime(2026, 5, 5, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )
    assert result == (0, 0, 0)
    mock_inner.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_profile_readme_returns_raw_markdown() -> None:
    client = _make_client()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "# Hello\n\nWorld"

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch.object(client, "_open_client", return_value=mock_http):
        result = await client.fetch_profile_readme("alice")

    assert result == "# Hello\n\nWorld"
    mock_http.get.assert_awaited_once()
    call_args = mock_http.get.await_args
    assert call_args.args[0] == "/repos/alice/alice/readme"


@pytest.mark.asyncio
async def test_fetch_profile_readme_returns_none_on_404() -> None:
    client = _make_client()
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch.object(client, "_open_client", return_value=mock_http):
        result = await client.fetch_profile_readme("alice")

    assert result is None


@pytest.mark.asyncio
async def test_contribution_totals_for_range_rejects_user_login_mismatch() -> None:
    client = _make_client()
    mock_http = AsyncMock()

    with patch.object(
        client,
        "_graphql_request",
        new=AsyncMock(
            return_value={
                "user": {
                    "login": "wrong-user",
                    "contributionsCollection": {
                        "totalCommitContributions": 99,
                        "totalPullRequestContributions": 0,
                        "totalPullRequestReviewContributions": 0,
                    },
                }
            }
        ),
    ):
        with pytest.raises(GitHubAPIError, match="does not match requested login"):
            await client._contribution_totals_for_range(
                mock_http,
                "alice",
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
            )


@pytest.mark.asyncio
async def test_contribution_totals_for_range_raises_when_user_missing() -> None:
    client = _make_client()
    mock_http = AsyncMock()

    with patch.object(client, "_graphql_request", new=AsyncMock(return_value={"user": None})):
        with pytest.raises(GitHubUserNotFoundError):
            await client._contribution_totals_for_range(
                mock_http,
                "missing-user",
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
            )
