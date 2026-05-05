"""POST /me/sync — persisted score sync with cooldown and delta progress."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.github import GitHubAPIError, GitHubClient
from app.domain.datetime_github import parse_github_datetime
from app.domain.github_inputs import GithubScoreInputs
from app.domain.scoring import (
    XpBreakdownContribution,
    XpProgress,
    calculate_xp,
    stars_after_single_repo_cap,
)
from app.models.developer import Developer
from app.repositories.developer import DeveloperRepository
from app.schemas.score import (
    GithubPublicScoreResponse,
    XpProgressSchema,
    public_score_response_from,
)
from app.schemas.sync_score import ScoreSyncProgressSchema, ScoreXpBreakdownDeltaSchema
from app.services.github_score_service import (
    github_snapshot_from_developer_row,
    github_snapshot_from_inputs,
)

SYNC_COOLDOWN = timedelta(hours=6)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MeSyncCooldown:
    retry_after: datetime


@dataclass(frozen=True, slots=True)
class MeSyncPerformed:
    first_sync: bool
    payload: GithubPublicScoreResponse
    progress: ScoreSyncProgressSchema | None


def _breakdown_delta_points(
    before: XpBreakdownContribution,
    after: XpBreakdownContribution,
) -> ScoreXpBreakdownDeltaSchema:
    return ScoreXpBreakdownDeltaSchema(
        commits=after.from_commits - before.from_commits,
        pull_requests=after.from_pull_requests - before.from_pull_requests,
        reviews=after.from_reviews - before.from_reviews,
        stars=after.from_stars - before.from_stars,
        forks=after.from_forks - before.from_forks,
        followers=after.from_followers - before.from_followers,
        tenure_years_bonus=after.from_tenure - before.from_tenure,
    )


def _xp_progress_schema(progress: XpProgress) -> XpProgressSchema:
    return XpProgressSchema(
        level=progress.level,
        xp_in_level=progress.xp_in_level,
        xp_needed=progress.xp_needed,
        percent=progress.percent,
    )


class ScoreSyncService:
    def __init__(self, github: GitHubClient) -> None:
        self._github = github

    async def sync_for_github_login(
        self,
        db: AsyncSession,
        *,
        github_login: str,
    ) -> MeSyncCooldown | MeSyncPerformed:
        """Resolve GitHub user id + canonical login, then run persisted sync."""
        trimmed = github_login.strip()
        if not trimmed:
            raise ValueError("GitHub login cannot be empty")
        profile = await self._github.fetch_public_user_profile(trimmed)
        raw_id = profile.get("id")
        if raw_id is None:
            raise GitHubAPIError("Missing user id in GitHub /users response")
        github_id = int(raw_id)
        login = str(profile.get("login", trimmed))
        return await self.sync_for_actor(db, github_id=github_id, login=login)

    async def sync_for_actor(
        self,
        db: AsyncSession,
        *,
        github_id: int,
        login: str,
    ) -> MeSyncCooldown | MeSyncPerformed:
        repo = DeveloperRepository(db)
        trimmed = login.strip()
        now = datetime.now(tz=UTC)

        row = await repo.get_by_github_id(github_id)
        if row is not None and row.last_sync_at is not None:
            raw_last = row.last_sync_at
            last_sync = raw_last if raw_last.tzinfo else raw_last.replace(tzinfo=UTC)
            last_sync = last_sync.astimezone(UTC)
            if now - last_sync < SYNC_COOLDOWN:
                return MeSyncCooldown(retry_after=last_sync + SYNC_COOLDOWN)

        if row is None:
            inputs = await self._github.fetch_score_inputs(trimmed)
            stars_raw, stars_capped = stars_after_single_repo_cap(inputs.stars_per_repo)
            xp, _ = calculate_xp(inputs)
            created = Developer(
                github_id=github_id,
                github_login=trimmed,
                commits_alltime=inputs.commits_alltime,
                prs_contributions_alltime=inputs.prs_contributions_alltime,
                reviews_alltime=inputs.reviews_alltime,
                forks_received=inputs.forks_received,
                followers=inputs.followers,
                stars_received_raw=stars_raw,
                stars_received_capped=stars_capped,
                owned_non_fork_repos_count=len(inputs.stars_per_repo),
                account_created_at=inputs.account_created_at,
                xp_brut=xp,
                last_sync_at=now,
                created_at=now,
                updated_at=now,
            )
            await repo.create(created)
            await db.commit()

            snap = github_snapshot_from_inputs(trimmed, inputs)
            return MeSyncPerformed(
                first_sync=True,
                payload=public_score_response_from(snap),
                progress=None,
            )

        prev_snap = github_snapshot_from_developer_row(trimmed, row)
        prev_xp = prev_snap.xp
        prev_level = prev_snap.xp_progress.level
        prev_breakdown = prev_snap.xp_breakdown

        last = row.last_sync_at or row.created_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        last = last.astimezone(UTC)
        range_from = min(last + timedelta(seconds=1), now)

        dc, dpr, drv = await self._github.contributions_totals_between(trimmed, range_from, now)
        logger.debug(
            "incremental delta for %r range=[%s → %s]: commits=%d prs=%d reviews=%d",
            trimmed,
            range_from.isoformat(),
            now.isoformat(),
            dc,
            dpr,
            drv,
        )

        profile = await self._github.fetch_public_user_profile(trimmed)
        created_at = parse_github_datetime(str(profile["created_at"]))
        stars_per_repo, forks_received = await self._github.fetch_owner_repo_star_fork_totals(
            trimmed,
        )
        stars_raw, stars_capped = stars_after_single_repo_cap(stars_per_repo)

        row.commits_alltime += dc
        row.prs_contributions_alltime += dpr
        row.reviews_alltime += drv
        row.followers = int(profile.get("followers", 0))
        row.forks_received = forks_received
        row.stars_received_raw = stars_raw
        row.stars_received_capped = stars_capped
        row.owned_non_fork_repos_count = len(stars_per_repo)
        row.account_created_at = created_at
        row.github_login = str(profile.get("login", trimmed))
        row.last_sync_at = now
        row.updated_at = now

        inputs = GithubScoreInputs(
            commits_alltime=row.commits_alltime,
            prs_contributions_alltime=row.prs_contributions_alltime,
            reviews_alltime=row.reviews_alltime,
            stars_per_repo=stars_per_repo,
            forks_received=forks_received,
            followers=int(profile.get("followers", 0)),
            account_created_at=created_at,
        )
        xp, new_breakdown = calculate_xp(inputs)
        row.xp_brut = xp

        await db.commit()

        after_snap = github_snapshot_from_inputs(trimmed, inputs)
        body = public_score_response_from(after_snap)

        progress = ScoreSyncProgressSchema(
            xp_before=prev_xp,
            xp_after=after_snap.xp,
            level_before=prev_level,
            level_after=after_snap.xp_progress.level,
            cell_before=prev_snap.cell_count,
            cell_after=after_snap.cell_count,
            xp_progress_before=_xp_progress_schema(prev_snap.xp_progress),
            xp_progress_after=_xp_progress_schema(after_snap.xp_progress),
            breakdown_delta=_breakdown_delta_points(prev_breakdown, new_breakdown),
        )
        return MeSyncPerformed(first_sync=False, payload=body, progress=progress)
