from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.github_inputs import GitHubScoreInputs
from app.domain.score_snapshot import GitHubPublicScoreSnapshot, github_snapshot_from_inputs

if TYPE_CHECKING:
    from app.clients.github import GitHubStatsFetcher


class GitHubScoreService:
    def __init__(self, github: GitHubStatsFetcher) -> None:
        self._github = github

    async def build_public_snapshot(self, login: str) -> GitHubPublicScoreSnapshot:
        fetch_login = login.strip()
        github_inputs: GitHubScoreInputs = await self._github.fetch_score_inputs(fetch_login)
        return github_snapshot_from_inputs(fetch_login, github_inputs)
