from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.domain.datetime_github import parse_github_datetime
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.github_repo_stats import merge_repo_stats, repo_stats_from_pages
from app.domain.scoring import evaluate_commits_farm_flag


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
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
    }
  }
}
"""

GRAPHQL_COMMIT_BREAKDOWN_SLICE = """
query CommitBreakdownSlice($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      commitContributionsByRepository(maxRepositories: 100) {
        contributions { totalCount }
      }
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

    async def fetch_profile_readme(self, login: str) -> str | None:
        """Return raw markdown from the user's profile README repo, or None if missing."""
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
            r = await client.get(
                f"/repos/{login}/{login}/readme",
                headers={**self._headers(), "Accept": "application/vnd.github.raw"},
            )
            if r.status_code == 404:
                return None
            self._handle_rest_status(r, login)
            return r.text

    async def contributions_totals_between(
        self,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> tuple[int, int, int, int]:
        """Sum contribution counts for [range_from, range_to] with per-calendar-year GraphQL calls.

        GitHub clamps ``from`` to within one year of ``to`` on a single query; slicing avoids loss.
        All year-slices are fired in parallel via asyncio.gather.

        Returns (commits, prs, reviews, private_contributions).
        """
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()
        if range_from > range_to:
            return (0, 0, 0, 0)

        async with self._open_client() as client:
            return await self._contributions_year_slices_between(
                client, login, range_from, range_to
            )

    async def commit_breakdown_sum_between(
        self,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> int:
        """Sum visible commit counts from commitContributionsByRepository across year-slices."""
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()
        if range_from > range_to:
            return 0

        async with self._open_client() as client:
            return await self._commit_breakdown_year_slices_between(
                client, login, range_from, range_to
            )

    async def fetch_owner_repo_star_fork_totals(
        self,
        login: str,
        *,
        include_org_admin_repos: bool = False,
    ) -> tuple[tuple[int, ...], int]:
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
            return await self._repos_aggregates(
                client,
                login,
                include_org_admin=include_org_admin_repos,
            )

    async def _contribution_totals_for_range(
        self,
        client: httpx.AsyncClient,
        login: str,
        chunk_from: datetime,
        chunk_to: datetime,
    ) -> tuple[int, int, int, int]:
        payload = await self._graphql_request(
            client,
            GRAPHQL_SCORE_SLICE,
            {
                "login": login,
                "from": _github_datetime(chunk_from),
                "to": _github_datetime(chunk_to),
            },
        )
        node = payload.get("user") if isinstance(payload, dict) else None
        if node is None:
            raise GitHubUserNotFoundError(login)
        resolved_login = node.get("login")
        if isinstance(resolved_login, str) and resolved_login.lower() != login.lower():
            raise GitHubAPIError(
                f"GitHub user login {resolved_login!r} does not match requested login {login!r}"
            )
        cc = node.get("contributionsCollection") or {}
        public_commits = int(cc.get("totalCommitContributions", 0) or 0)
        # Private/internal activity the token cannot detail is exposed only as an aggregate
        # count when the user enabled "private contributions" on their GitHub profile.
        restricted = int(cc.get("restrictedContributionsCount", 0) or 0)
        return (
            public_commits,
            int(cc.get("totalPullRequestContributions", 0) or 0),
            int(cc.get("totalPullRequestReviewContributions", 0) or 0),
            restricted,
        )

    async def fetch_score_inputs(
        self,
        login: str,
        *,
        include_org_admin_repos: bool = False,
    ) -> GitHubScoreInputs:
        login = login.strip()
        if not login:
            raise InvalidGitHubLoginError()

        async with self._open_client() as client:
            profile = await self._fetch_user_profile(client, login)
            created_at = parse_github_datetime(profile["created_at"])
            public_repos: int | None = profile.get("public_repos")

            (
                (commits, prs, reviews, private),
                (stars_per_repo, forks_received),
                breakdown_sum,
            ) = await asyncio.gather(
                self._contributions_year_slices(client, login, created_at),
                self._repos_aggregates(
                    client,
                    login,
                    total_repos_hint=public_repos,
                    include_org_admin=include_org_admin_repos,
                ),
                self._commit_breakdown_year_slices(client, login, created_at),
            )

            farm_flagged = evaluate_commits_farm_flag(commits, breakdown_sum)

            return GitHubScoreInputs(
                commits_alltime=commits,
                prs_contributions_alltime=prs,
                reviews_alltime=reviews,
                private_contributions_alltime=private,
                stars_per_repo=stars_per_repo,
                forks_received=forks_received,
                followers=int(profile.get("followers", 0)),
                account_created_at=created_at,
                commits_breakdown_sum=breakdown_sum,
                commits_farm_flagged=farm_flagged,
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
    ) -> tuple[int, int, int, int]:
        now = datetime.now(tz=UTC)
        return await self._contributions_year_slices_between(client, login, created_at, now)

    async def _contributions_year_slices_between(
        self,
        client: httpx.AsyncClient,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> tuple[int, int, int, int]:
        """Fire one GraphQL query per calendar year in parallel and aggregate results."""
        chunks: list[tuple[datetime, datetime]] = []
        for year in range(range_from.year, range_to.year + 1):
            chunk_from = max(range_from, datetime(year, 1, 1, tzinfo=UTC))
            chunk_to = min(range_to, datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC))
            if chunk_from > chunk_to:
                continue
            chunks.append((chunk_from, chunk_to))

        if not chunks:
            return (0, 0, 0, 0)

        results = await asyncio.gather(
            *[self._contribution_totals_for_range(client, login, cf, ct) for cf, ct in chunks]
        )
        total_commits = sum(r[0] for r in results)
        total_prs = sum(r[1] for r in results)
        total_reviews = sum(r[2] for r in results)
        total_private = sum(r[3] for r in results)
        return (total_commits, total_prs, total_reviews, total_private)

    async def _commit_breakdown_year_slices(
        self,
        client: httpx.AsyncClient,
        login: str,
        created_at: datetime,
    ) -> int:
        now = datetime.now(tz=UTC)
        return await self._commit_breakdown_year_slices_between(client, login, created_at, now)

    async def _commit_breakdown_year_slices_between(
        self,
        client: httpx.AsyncClient,
        login: str,
        range_from: datetime,
        range_to: datetime,
    ) -> int:
        chunks: list[tuple[datetime, datetime]] = []
        for year in range(range_from.year, range_to.year + 1):
            chunk_from = max(range_from, datetime(year, 1, 1, tzinfo=UTC))
            chunk_to = min(range_to, datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC))
            if chunk_from > chunk_to:
                continue
            chunks.append((chunk_from, chunk_to))

        if not chunks:
            return 0

        results = await asyncio.gather(
            *[self._commit_breakdown_sum_for_range(client, login, cf, ct) for cf, ct in chunks]
        )
        return sum(results)

    async def _commit_breakdown_sum_for_range(
        self,
        client: httpx.AsyncClient,
        login: str,
        chunk_from: datetime,
        chunk_to: datetime,
    ) -> int:
        payload = await self._graphql_request(
            client,
            GRAPHQL_COMMIT_BREAKDOWN_SLICE,
            {
                "login": login,
                "from": _github_datetime(chunk_from),
                "to": _github_datetime(chunk_to),
            },
        )
        node = payload.get("user") if isinstance(payload, dict) else None
        if node is None:
            raise GitHubUserNotFoundError(login)
        resolved_login = node.get("login")
        if isinstance(resolved_login, str) and resolved_login.lower() != login.lower():
            raise GitHubAPIError(
                f"GitHub user login {resolved_login!r} does not match requested login {login!r}"
            )
        cc = node.get("contributionsCollection") or {}
        total = 0
        for entry in cc.get("commitContributionsByRepository") or []:
            if not isinstance(entry, dict):
                continue
            contrib = entry.get("contributions") or {}
            total += int(contrib.get("totalCount", 0) or 0)
        return total

    async def _repos_aggregates(
        self,
        client: httpx.AsyncClient,
        login: str,
        total_repos_hint: int | None = None,
        *,
        include_org_admin: bool = False,
    ) -> tuple[tuple[int, ...], int]:
        """Fetch personal owner repos and optionally org repos where the token holder is admin."""
        if total_repos_hint is not None and total_repos_hint > 0:
            pages = await self._personal_repo_pages_parallel(client, login, total_repos_hint)
        else:
            pages = await self._personal_repo_pages_sequential(client, login)

        personal_stats = repo_stats_from_pages(pages)
        if not include_org_admin:
            return merge_repo_stats(personal_stats)

        org_stats = await self._org_admin_repo_stats(client)
        return merge_repo_stats(personal_stats, org_stats)

    async def _org_admin_repo_stats(self, client: httpx.AsyncClient) -> dict[str, tuple[int, int]]:
        admin_orgs = await self._org_admin_org_logins(client)
        if not admin_orgs:
            return {}

        org_repo_pages = await asyncio.gather(
            *[self._org_repo_pages(client, org_login) for org_login in admin_orgs]
        )
        flat_pages = [page for pages in org_repo_pages for page in pages]
        return repo_stats_from_pages(flat_pages)

    async def _org_admin_org_logins(self, client: httpx.AsyncClient) -> list[str]:
        admin_orgs: list[str] = []
        page = 1
        while True:
            batch = await self._fetch_org_memberships_page(client, page)
            if not batch:
                break
            for membership in batch:
                if not isinstance(membership, dict):
                    continue
                if membership.get("role") != "admin":
                    continue
                organization = membership.get("organization")
                if not isinstance(organization, dict):
                    continue
                org_login = organization.get("login")
                if isinstance(org_login, str) and org_login.strip():
                    admin_orgs.append(org_login.strip())
            if len(batch) < 100:
                break
            page += 1
        return admin_orgs

    async def _fetch_org_memberships_page(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[dict[str, Any]]:
        r = await client.get(
            "/user/memberships/orgs",
            params={"state": "active", "per_page": 100, "page": page},
        )
        if r.status_code >= 400:
            raise GitHubAPIError(f"REST HTTP {r.status_code}: {r.text}")
        memberships = r.json()
        if not isinstance(memberships, list):
            raise GitHubAPIError("Invalid /user/memberships/orgs response body")
        return memberships

    async def _org_repo_pages(
        self,
        client: httpx.AsyncClient,
        org_login: str,
    ) -> list[list[dict[str, Any]]]:
        pages: list[list[dict[str, Any]]] = []
        page = 1
        while True:
            batch = await self._fetch_org_repos_page(client, org_login, page)
            if not batch:
                break
            pages.append(batch)
            if len(batch) < 100:
                break
            page += 1
        return pages

    async def _fetch_org_repos_page(
        self,
        client: httpx.AsyncClient,
        org_login: str,
        page: int,
    ) -> list[dict[str, Any]]:
        r = await client.get(
            f"/orgs/{org_login}/repos",
            params={
                "type": "all",
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            },
        )
        self._handle_rest_status(r, org_login)
        batch = r.json()
        if not isinstance(batch, list):
            raise GitHubAPIError("Invalid /orgs/repos response body")
        return batch

    async def _personal_repo_pages_parallel(
        self,
        client: httpx.AsyncClient,
        login: str,
        total_repos_hint: int,
    ) -> list[list[dict[str, Any]]]:
        total_pages = math.ceil(total_repos_hint / 100)
        pages = list(
            await asyncio.gather(
                *[self._fetch_repos_page(client, login, p) for p in range(1, total_pages + 1)]
            )
        )
        last_page = pages[-1] if pages else []
        if len(last_page) == 100:
            extra_page = total_pages + 1
            while True:
                batch = await self._fetch_repos_page(client, login, extra_page)
                pages.append(batch)
                if len(batch) < 100:
                    break
                extra_page += 1
        return pages

    async def _personal_repo_pages_sequential(
        self,
        client: httpx.AsyncClient,
        login: str,
    ) -> list[list[dict[str, Any]]]:
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
        return pages

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
