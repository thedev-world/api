"""POST /me/sync — persisted score sync with cooldown and delta progress."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.github import GitHubAPIError, GitHubClient
from app.domain.datetime_github import parse_github_datetime
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.github_profile import sync_avatar_url_from_profile
from app.domain.score_snapshot import (
    GitHubPublicScoreSnapshot,
    SyncProgress,
    github_snapshot_from_developer_row,
    github_snapshot_from_inputs,
)
from app.domain.scoring import (
    calculate_xp,
    evaluate_commits_farm_flag,
    stars_after_single_repo_cap,
)
from app.models.developer import Developer
from app.repositories.developer import DeveloperRepository

SYNC_COOLDOWN = timedelta(hours=6)

logger = logging.getLogger(__name__)


def reset_sync_cooldown(row: Developer, *, now: datetime) -> None:
    """Allow immediate POST /me/sync after OAuth token or scope changes."""
    row.last_sync_at = now - SYNC_COOLDOWN - timedelta(seconds=1)


def _include_org_admin_repos(row: Developer | None) -> bool:
    """Org repo stars require the developer's OAuth token (read:org)."""
    return bool(row is not None and row.github_token)


def _apply_commit_farm_fields(
    row: Developer,
    *,
    commits_alltime: int,
    breakdown_sum: int,
) -> None:
    row.commits_breakdown_sum = breakdown_sum
    row.commits_farm_flagged = evaluate_commits_farm_flag(commits_alltime, breakdown_sum)


def _score_inputs_from_row(
    row: Developer,
    *,
    stars_per_repo: tuple[int, ...],
    forks_received: int,
    followers: int,
    account_created_at: datetime,
) -> GitHubScoreInputs:
    return GitHubScoreInputs(
        commits_alltime=row.commits_alltime,
        prs_contributions_alltime=row.prs_contributions_alltime,
        reviews_alltime=row.reviews_alltime,
        private_contributions_alltime=row.private_contributions_alltime,
        stars_per_repo=stars_per_repo,
        forks_received=forks_received,
        followers=followers,
        account_created_at=account_created_at,
        commits_breakdown_sum=row.commits_breakdown_sum,
        commits_farm_flagged=row.commits_farm_flagged,
        commits_farm_cleared=row.commits_farm_cleared,
    )


@dataclass(frozen=True, slots=True)
class MeSyncCooldown:
    retry_after: datetime


@dataclass(frozen=True, slots=True)
class MeSyncPerformed:
    first_sync: bool
    snapshot: GitHubPublicScoreSnapshot
    progress: SyncProgress | None


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

        github = self._github.with_token(row.github_token if row is not None else None)
        include_org_repos = _include_org_admin_repos(row)

        if row is not None and row.last_sync_at is not None:
            raw_last = row.last_sync_at
            last_sync = raw_last if raw_last.tzinfo else raw_last.replace(tzinfo=UTC)
            last_sync = last_sync.astimezone(UTC)
            if now - last_sync < SYNC_COOLDOWN:
                return MeSyncCooldown(retry_after=last_sync + SYNC_COOLDOWN)

        needs_full_backfill = row is None or row.last_sync_at is None
        if needs_full_backfill:
            inputs, profile = await asyncio.gather(
                github.fetch_score_inputs(trimmed, include_org_admin_repos=include_org_repos),
                github.fetch_public_user_profile(trimmed),
            )
            stars_raw, stars_capped = stars_after_single_repo_cap(inputs.stars_per_repo)
            xp, _ = calculate_xp(inputs)
            if row is None:
                created = Developer(
                    github_id=github_id,
                    github_login=trimmed,
                    commits_alltime=inputs.commits_alltime,
                    commits_breakdown_sum=inputs.commits_breakdown_sum,
                    commits_farm_flagged=inputs.commits_farm_flagged,
                    prs_contributions_alltime=inputs.prs_contributions_alltime,
                    reviews_alltime=inputs.reviews_alltime,
                    private_contributions_alltime=inputs.private_contributions_alltime,
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
            else:
                row.commits_alltime = inputs.commits_alltime
                row.commits_breakdown_sum = inputs.commits_breakdown_sum
                row.commits_farm_flagged = inputs.commits_farm_flagged
                row.prs_contributions_alltime = inputs.prs_contributions_alltime
                row.reviews_alltime = inputs.reviews_alltime
                row.private_contributions_alltime = inputs.private_contributions_alltime
                row.forks_received = inputs.forks_received
                row.followers = inputs.followers
                row.stars_received_raw = stars_raw
                row.stars_received_capped = stars_capped
                row.owned_non_fork_repos_count = len(inputs.stars_per_repo)
                row.account_created_at = inputs.account_created_at
                row.github_login = trimmed
                row.xp_brut = xp
                row.last_sync_at = now
                row.updated_at = now
            target = row if row is not None else created
            sync_avatar_url_from_profile(target, profile)
            await db.commit()

            snap = github_snapshot_from_inputs(trimmed, inputs)
            return MeSyncPerformed(first_sync=True, snapshot=snap, progress=None)

        prev_snap = github_snapshot_from_developer_row(trimmed, row)
        prev_breakdown = prev_snap.xp_breakdown

        account_created_at = row.account_created_at
        if account_created_at.tzinfo is None:
            account_created_at = account_created_at.replace(tzinfo=UTC)
        account_created_at = account_created_at.astimezone(UTC)

        (
            (fresh_commits, fresh_prs, fresh_reviews, fresh_private),
            profile,
            (stars_per_repo, forks_received),
            breakdown_sum,
        ) = await asyncio.gather(
            github.contributions_totals_between(trimmed, account_created_at, now),
            github.fetch_public_user_profile(trimmed),
            github.fetch_owner_repo_star_fork_totals(
                trimmed,
                include_org_admin_repos=include_org_repos,
            ),
            github.commit_breakdown_sum_between(trimmed, account_created_at, now),
        )
        logger.debug(
            "incremental refresh for %r alltime from %s: commits %d→%d prs %d→%d \
            reviews %d→%d private %d→%d",
            trimmed,
            account_created_at.isoformat(),
            row.commits_alltime,
            fresh_commits,
            row.prs_contributions_alltime,
            fresh_prs,
            row.reviews_alltime,
            fresh_reviews,
            row.private_contributions_alltime,
            fresh_private,
        )

        created_at = parse_github_datetime(str(profile["created_at"]))
        stars_raw, stars_capped = stars_after_single_repo_cap(stars_per_repo)

        row.commits_alltime = fresh_commits
        row.prs_contributions_alltime = fresh_prs
        row.reviews_alltime = fresh_reviews
        row.private_contributions_alltime = fresh_private
        _apply_commit_farm_fields(
            row,
            commits_alltime=fresh_commits,
            breakdown_sum=breakdown_sum,
        )
        row.followers = int(profile.get("followers", 0))
        row.forks_received = forks_received
        row.stars_received_raw = stars_raw
        row.stars_received_capped = stars_capped
        row.owned_non_fork_repos_count = len(stars_per_repo)
        row.account_created_at = created_at
        row.github_login = str(profile.get("login", trimmed))
        row.last_sync_at = now
        row.updated_at = now

        inputs = _score_inputs_from_row(
            row,
            stars_per_repo=stars_per_repo,
            forks_received=forks_received,
            followers=int(profile.get("followers", 0)),
            account_created_at=created_at,
        )
        xp, new_breakdown = calculate_xp(inputs)
        row.xp_brut = xp

        sync_avatar_url_from_profile(row, profile)
        await db.commit()

        after_snap = github_snapshot_from_inputs(trimmed, inputs)

        progress = SyncProgress(
            xp_before=prev_snap.xp,
            xp_after=after_snap.xp,
            level_before=prev_snap.xp_progress.level,
            level_after=after_snap.xp_progress.level,
            cell_before=prev_snap.cell_count,
            cell_after=after_snap.cell_count,
            xp_progress_before=prev_snap.xp_progress,
            xp_progress_after=after_snap.xp_progress,
            breakdown_before=prev_breakdown,
            breakdown_after=new_breakdown,
        )
        return MeSyncPerformed(first_sync=False, snapshot=after_snap, progress=progress)
