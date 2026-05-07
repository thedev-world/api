from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.domain.datetime_github import parse_github_datetime
from app.domain.github_inputs import GitHubScoreInputs


class GitHubUserNotFoundError(Exception):
    def __init__(self, login: str) -> None:
        super().__init__(f"GitHub user not found: {login!r}")
        self.login = login


class GitHubRateLimitError(Exception):
    pass


class GitHubAPIError(Exception):
    pass


GRAPHQL_SCORE_SLICE = """
query ContributionSlice($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
    }
  }
}
"""


class GitHubStatsFetcher(Protocol):
    async def fetch_score_inputs(self, login: str) -> GitHubScoreInputs: ...


class GitHubClient(GitHubStatsFetcher):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._settings.github_token:
            h["Authorization"] = f"Bearer {self._settings.github_token}"
        return h

    async def fetch_public_user_profile(self, login: str) -> dict[str, Any]:
        login = login.strip()
        if not login:
            raise ValueError("GitHub login cannot be empty")

        base = self._settings.github_api_base.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base,
            headers=self._headers(),
            timeout=httpx.Timeout(45.0),
        ) as client:
            return await self._fetch_user_profile(client, login)

    async def contributions_totals_between(
        self,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> tuple[int, int, int]:
        """Sum contribution counts for [range_from, range_to] with per-calendar-year GraphQL calls.

        GitHub clamps ``from`` to within one year of ``to`` on a single query; slicing avoids loss.
        """
        login = login.strip()
        if not login:
            raise ValueError("GitHub login cannot be empty")
        if range_from > range_to:
            return (0, 0, 0)

        base = self._settings.github_api_base.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base,
            headers=self._headers(),
            timeout=httpx.Timeout(45.0),
        ) as client:
            total_commits = 0
            total_prs = 0
            total_reviews = 0
            for year in range(range_from.year, range_to.year + 1):
                chunk_from = max(range_from, datetime(year, 1, 1, tzinfo=UTC))
                chunk_to = min(range_to, datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC))
                if chunk_from > chunk_to:
                    continue
                dc, dpr, drv = await self._contribution_totals_for_range(
                    client, login, chunk_from, chunk_to
                )
                total_commits += dc
                total_prs += dpr
                total_reviews += drv
            return (total_commits, total_prs, total_reviews)

    async def fetch_owner_repo_star_fork_totals(self, login: str) -> tuple[tuple[int, ...], int]:
        login = login.strip()
        if not login:
            raise ValueError("GitHub login cannot be empty")

        base = self._settings.github_api_base.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base,
            headers=self._headers(),
            timeout=httpx.Timeout(45.0),
        ) as client:
            return await self._repos_aggregates(client, login)

    async def _contribution_totals_for_range(
        self,
        client: httpx.AsyncClient,
        login: str,
        chunk_from: datetime,
        chunk_to: datetime,
    ) -> tuple[int, int, int]:
        payload = await self._graphql_request(
            client,
            GRAPHQL_SCORE_SLICE,
            {
                "login": login,
                "from": _github_datetime(chunk_from),
                "to": _github_datetime(chunk_to),
            },
        )
        viewer_user = payload.get("user") if isinstance(payload, dict) else None
        if viewer_user is None:
            raise GitHubUserNotFoundError(login)
        cc = viewer_user.get("contributionsCollection") or {}
        return (
            int(cc.get("totalCommitContributions", 0) or 0),
            int(cc.get("totalPullRequestContributions", 0) or 0),
            int(cc.get("totalPullRequestReviewContributions", 0) or 0),
        )

    async def fetch_score_inputs(self, login: str) -> GitHubScoreInputs:
        login = login.strip()
        if not login:
            raise ValueError("GitHub login cannot be empty")

        base = self._settings.github_api_base.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base,
            headers=self._headers(),
            timeout=httpx.Timeout(45.0),
        ) as client:
            profile = await self._fetch_user_profile(client, login)
            created_at = parse_github_datetime(profile["created_at"])

            commits, prs, reviews = await self._contributions_year_slices(client, login, created_at)

            stars_per_repo, forks_received = await self._repos_aggregates(client, login)

            return GitHubScoreInputs(
                commits_alltime=commits,
                prs_contributions_alltime=prs,
                reviews_alltime=reviews,
                stars_per_repo=stars_per_repo,
                forks_received=forks_received,
                followers=int(profile.get("followers", 0)),
                account_created_at=created_at,
            )

    async def _fetch_user_profile(self, client: httpx.AsyncClient, login: str) -> dict[str, Any]:
        r = await client.get(f"/users/{login}")
        self._handle_rest_status(r, login)
        data = r.json()
        if not isinstance(data, dict):
            raise GitHubAPIError("Invalid /users response body")
        return data

    async def _contributions_year_slices(
        self,
        client: httpx.AsyncClient,
        login: str,
        created_at: datetime,
    ) -> tuple[int, int, int]:
        now = datetime.now(tz=UTC)
        total_commits = 0
        total_prs = 0
        total_reviews = 0

        for year in range(created_at.year, now.year + 1):
            year_start = datetime(year, 1, 1, tzinfo=UTC)
            year_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
            chunk_from = max(created_at, year_start)
            chunk_to = min(now, year_end)
            if chunk_from > chunk_to:
                continue

            commits, prs, reviews = await self._contribution_totals_for_range(
                client,
                login,
                chunk_from,
                chunk_to,
            )
            total_commits += commits
            total_prs += prs
            total_reviews += reviews

        return total_commits, total_prs, total_reviews

    async def _repos_aggregates(
        self,
        client: httpx.AsyncClient,
        login: str,
    ) -> tuple[tuple[int, ...], int]:
        stars_list: list[int] = []
        forks_received = 0
        page = 1

        while True:
            r = await client.get(
                f"/users/{login}/repos",
                params={
                    "type": "owner",
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc",
                },
            )
            self._handle_rest_status(r, login)
            batch = r.json()
            if not isinstance(batch, list):
                raise GitHubAPIError("Invalid /repos response body")
            if not batch:
                break

            for repo in batch:
                if not isinstance(repo, dict):
                    continue
                if repo.get("fork"):
                    continue
                stars = int(repo.get("stargazers_count", 0) or 0)
                stars_list.append(stars)
                forks_received += int(repo.get("forks_count", 0) or 0)

            if len(batch) < 100:
                break
            page += 1

        return (tuple(stars_list), forks_received)

    async def _graphql_request(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        r = await client.post(
            "/graphql",
            json={"query": query, "variables": variables},
        )
        if r.status_code in (403, 429):
            raise GitHubRateLimitError(r.text)
        if r.status_code >= 400:
            raise GitHubAPIError(f"GraphQL HTTP {r.status_code}: {r.text}")
        body = r.json()
        if not isinstance(body, dict):
            raise GitHubAPIError("Invalid GraphQL JSON body")
        errors = body.get("errors")
        if errors:
            raise GitHubAPIError(str(errors))
        data = body.get("data")
        if not isinstance(data, dict):
            raise GitHubAPIError("Missing GraphQL data")
        return data

    def _handle_rest_status(self, r: httpx.Response, login: str) -> None:
        if r.status_code == 404:
            raise GitHubUserNotFoundError(login)
        if r.status_code in (403, 429):
            raise GitHubRateLimitError(r.text)
        if r.status_code >= 400:
            raise GitHubAPIError(f"REST HTTP {r.status_code}: {r.text}")


def _github_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    s = dt.astimezone(UTC).isoformat()
    return s.replace("+00:00", "Z")
