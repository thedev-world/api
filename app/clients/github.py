from __future__ import annotations

import asyncio
import math
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


class InvalidGitHubLoginError(Exception):
    pass


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
    def __init__(self, settings: Settings, *, token: str | None = None) -> None:
        self._settings = settings
        self._token = token or settings.github_token

    def with_token(self, token: str | None) -> GitHubClient:
        """Return a new client using the given user token, falling back to the global one."""
        return GitHubClient(self._settings, token=token)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _open_client(self) -> httpx.AsyncClient:
        """Return a configured AsyncClient. Caller is responsible for closing it."""
        base = self._settings.github_api_base.rstrip("/")
        return httpx.AsyncClient(
            base_url=base,
            headers=self._headers(),
            timeout=httpx.Timeout(45.0),
        )

    async def fetch_public_user_profile(self, login: str) -> dict[str, Any]:
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
            return await self._fetch_user_profile(client, login)

    async def contributions_totals_between(
        self,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> tuple[int, int, int]:
        """Sum contribution counts for [range_from, range_to] with per-calendar-year GraphQL calls.

        GitHub clamps ``from`` to within one year of ``to`` on a single query; slicing avoids loss.
        All year-slices are fired in parallel via asyncio.gather.
        """
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()
        if range_from > range_to:
            return (0, 0, 0)

        async with self._open_client() as client:
            return await self._contributions_year_slices_between(
                client, login, range_from, range_to
            )

    async def fetch_owner_repo_star_fork_totals(self, login: str) -> tuple[tuple[int, ...], int]:
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
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
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
            profile = await self._fetch_user_profile(client, login)
            created_at = parse_github_datetime(profile["created_at"])
            public_repos: int | None = profile.get("public_repos")

            (commits, prs, reviews), (stars_per_repo, forks_received) = await asyncio.gather(
                self._contributions_year_slices(client, login, created_at),
                self._repos_aggregates(client, login, total_repos_hint=public_repos),
            )

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
        return await self._contributions_year_slices_between(client, login, created_at, now)

    async def _contributions_year_slices_between(
        self,
        client: httpx.AsyncClient,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> tuple[int, int, int]:
        """Fire one GraphQL query per calendar year in parallel and aggregate results."""
        chunks: list[tuple[datetime, datetime]] = []
        for year in range(range_from.year, range_to.year + 1):
            chunk_from = max(range_from, datetime(year, 1, 1, tzinfo=UTC))
            chunk_to = min(range_to, datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC))
            if chunk_from > chunk_to:
                continue
            chunks.append((chunk_from, chunk_to))

        if not chunks:
            return (0, 0, 0)

        results = await asyncio.gather(
            *[self._contribution_totals_for_range(client, login, cf, ct) for cf, ct in chunks]
        )
        total_commits = sum(r[0] for r in results)
        total_prs = sum(r[1] for r in results)
        total_reviews = sum(r[2] for r in results)
        return (total_commits, total_prs, total_reviews)

    async def _repos_aggregates(
        self,
        client: httpx.AsyncClient,
        login: str,
        total_repos_hint: int | None = None,
    ) -> tuple[tuple[int, ...], int]:
        """Fetch all owner repos and return (stars_per_repo, total_forks).

        When total_repos_hint is provided (from /users profile), all pages are fired
        in parallel. Without a hint, falls back to sequential pagination.
        """
        if total_repos_hint is not None and total_repos_hint > 0:
            return await self._repos_aggregates_parallel(client, login, total_repos_hint)
        return await self._repos_aggregates_sequential(client, login)

    async def _fetch_repos_page(
        self,
        client: httpx.AsyncClient,
        login: str,
        page: int,
    ) -> list[dict[str, Any]]:
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
        return batch

    def _aggregate_repos(self, pages: list[list[dict[str, Any]]]) -> tuple[tuple[int, ...], int]:
        stars_list: list[int] = []
        forks_received = 0
        for batch in pages:
            for repo in batch:
                if not isinstance(repo, dict):
                    continue
                if repo.get("fork"):
                    continue
                stars_list.append(int(repo.get("stargazers_count", 0) or 0))
                forks_received += int(repo.get("forks_count", 0) or 0)
        return (tuple(stars_list), forks_received)

    async def _repos_aggregates_parallel(
        self,
        client: httpx.AsyncClient,
        login: str,
        total_repos_hint: int,
    ) -> tuple[tuple[int, ...], int]:
        total_pages = math.ceil(total_repos_hint / 100)
        pages = await asyncio.gather(
            *[self._fetch_repos_page(client, login, p) for p in range(1, total_pages + 1)]
        )
        # If the hint was stale and there are more repos, fetch additional pages sequentially
        last_page = pages[-1] if pages else []
        if len(last_page) == 100:
            extra_page = total_pages + 1
            while True:
                batch = await self._fetch_repos_page(client, login, extra_page)
                pages = (*pages, batch)
                if len(batch) < 100:
                    break
                extra_page += 1
        return self._aggregate_repos(list(pages))

    async def _repos_aggregates_sequential(
        self,
        client: httpx.AsyncClient,
        login: str,
    ) -> tuple[tuple[int, ...], int]:
        pages: list[list[dict[str, Any]]] = []
        page = 1
        while True:
            batch = await self._fetch_repos_page(client, login, page)
            if not batch:
                break
            pages.append(batch)
            if len(batch) < 100:
                break
            page += 1
        return self._aggregate_repos(pages)

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
