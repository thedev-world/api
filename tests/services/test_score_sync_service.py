"""Unit tests for ScoreSyncService branches (repository + GitHub mocked)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.domain.github_inputs import GithubScoreInputs
from app.domain.scoring import get_cell_count, get_xp_progress
from app.schemas.score import XpProgressSchema
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService
from tests.factories.developer_factory import make_developer


def _patch_now(fixed_now: datetime) -> MagicMock:
    mock_dm = MagicMock()
    mock_dm.now = MagicMock(return_value=fixed_now)
    mock_dm.UTC = UTC
    mock_dm.timedelta = timedelta
    return mock_dm


def _xp_progress_schema(progress: object) -> XpProgressSchema:
    return XpProgressSchema(
        level=progress.level,
        xp_in_level=progress.xp_in_level,
        xp_needed=progress.xp_needed,
        percent=progress.percent,
    )


@pytest.mark.asyncio
async def test_sync_cooldown_returns_me_sync_cooldown() -> None:
    last_sync = datetime(2030, 1, 10, 12, 0, 0, tzinfo=UTC)
    frozen_now = last_sync + timedelta(hours=1)
    row = make_developer(last_sync_at=last_sync, github_login="alice")

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        repo.create = AsyncMock()
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=row.github_id, login="alice")

        assert isinstance(out, MeSyncCooldown)
        assert out.retry_after == last_sync + timedelta(hours=6)
        db.commit.assert_not_awaited()
        repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_first_sync_creates_and_commits() -> None:
    fixed_now = datetime(2031, 2, 1, tzinfo=UTC)
    anchor = datetime(2015, 1, 1, tzinfo=UTC)
    inputs = GithubScoreInputs(
        commits_alltime=10,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_per_repo=(5,),
        forks_received=1,
        followers=7,
        account_created_at=anchor,
    )

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.fetch_score_inputs = AsyncMock(return_value=inputs)
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=None)
        repo.create = AsyncMock(side_effect=lambda d: d)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            out = await svc.sync_for_actor(db, github_id=99, login="bob")

        assert isinstance(out, MeSyncPerformed)
        assert out.first_sync is True
        assert out.progress is None
        assert out.payload.login == "bob"
        assert out.payload.xp >= 1
        repo.create.assert_called_once()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_incremental_sync_updates_row_and_returns_progress() -> None:
    last_sync = datetime(2030, 5, 1, 12, 0, 0, tzinfo=UTC)
    frozen_now = last_sync + timedelta(hours=8)
    row = make_developer(
        last_sync_at=last_sync,
        github_login="carol",
        github_id=777,
        commits_alltime=1,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_received_raw=0,
        stars_received_capped=0,
        forks_received=0,
        followers=0,
        xp_brut=0,
        owned_non_fork_repos_count=1,
        account_created_at=datetime(2014, 1, 1, tzinfo=UTC),
    )

    profile = {
        "id": 777,
        "login": "carol",
        "created_at": "2014-01-01T00:00:00Z",
        "followers": 0,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.contributions_totals_between = AsyncMock(return_value=(2, 0, 0))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((3,), 0))

    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        repo.create = AsyncMock()
        RepoCls.return_value = repo

        xp_before_incremental = row.xp_brut

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=777, login="carol")

        assert isinstance(out, MeSyncPerformed)
        assert out.first_sync is False
        assert out.progress is not None
        assert out.progress.xp_before == xp_before_incremental
        assert out.progress.xp_after == row.xp_brut == out.payload.xp
        assert out.progress.cell_before == get_cell_count(xp_before_incremental)
        assert out.progress.cell_after == out.payload.cell_count
        assert out.progress.xp_progress_before == _xp_progress_schema(
            get_xp_progress(xp_before_incremental),
        )
        assert out.progress.xp_progress_after == out.payload.xp_progress
        assert row.commits_alltime == 3
        assert row.stars_received_raw == 3
        gh.contributions_totals_between.assert_awaited_once_with(
            "carol",
            last_sync + timedelta(seconds=1),
            frozen_now,
        )
        d = out.progress.breakdown_delta
        assert d.commits == 20
        assert d.pull_requests == 0
        assert d.reviews == 0
        assert d.stars == 150
        assert d.forks == 0
        assert d.followers == 0
        assert d.tenure_years_bonus == 0
        repo.create.assert_not_called()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_incremental_sync_range_crosses_year_boundary() -> None:
    last_sync = datetime(2029, 12, 28, 10, 0, 0, tzinfo=UTC)
    frozen_now = datetime(2031, 2, 5, 10, 0, 0, tzinfo=UTC)
    row = make_developer(
        last_sync_at=last_sync,
        github_login="eve",
        github_id=888,
        commits_alltime=50,
        prs_contributions_alltime=10,
        reviews_alltime=5,
        stars_received_raw=0,
        stars_received_capped=0,
        forks_received=0,
        followers=0,
        xp_brut=0,
        owned_non_fork_repos_count=2,
        account_created_at=datetime(2018, 1, 1, tzinfo=UTC),
    )

    profile = {
        "id": 888,
        "login": "eve",
        "created_at": "2018-01-01T00:00:00Z",
        "followers": 0,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.contributions_totals_between = AsyncMock(return_value=(30, 8, 2))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((), 0))

    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        repo.create = AsyncMock()
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=888, login="eve")

        assert isinstance(out, MeSyncPerformed)
        expected_range_from = last_sync + timedelta(seconds=1)
        gh.contributions_totals_between.assert_awaited_once_with(
            "eve",
            expected_range_from,
            frozen_now,
        )
        assert row.commits_alltime == 50 + 30
        assert row.prs_contributions_alltime == 10 + 8
        assert row.reviews_alltime == 5 + 2
        d = out.progress.breakdown_delta
        assert d.commits == 30 * 10
        assert d.pull_requests == 8 * 30
        assert d.reviews == 2 * 15


@pytest.mark.asyncio
async def test_sync_for_github_login_resolves_id_from_profile() -> None:
    anchor = datetime(2016, 1, 1, tzinfo=UTC)
    inputs = GithubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        stars_per_repo=(),
        forks_received=0,
        followers=0,
        account_created_at=anchor,
    )

    fixed_now = datetime(2035, 1, 1, tzinfo=UTC)
    profile = {
        "id": 314159,
        "login": "dave",
        "created_at": "2016-01-01T00:00:00Z",
        "followers": 0,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_score_inputs = AsyncMock(return_value=inputs)
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=None)
        repo.create = AsyncMock(side_effect=lambda d: d)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            await svc.sync_for_github_login(db, github_login="Dave")

        repo.get_by_github_id.assert_awaited_once_with(314159)
