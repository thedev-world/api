"""Unit tests for ScoreSyncService branches (repository + GitHub mocked)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.domain.github_inputs import GitHubScoreInputs
from app.domain.scoring import get_cell_count, get_xp_progress
from app.services.score_sync_service import MeSyncCooldown, MeSyncPerformed, ScoreSyncService
from tests.factories.developer_factory import make_developer


def _patch_now(fixed_now: datetime) -> MagicMock:
    mock_dm = MagicMock()
    mock_dm.now = MagicMock(return_value=fixed_now)
    mock_dm.UTC = UTC
    mock_dm.timedelta = timedelta
    return mock_dm


@pytest.mark.asyncio
async def test_sync_cooldown_returns_me_sync_cooldown() -> None:
    last_sync = datetime(2030, 1, 10, 12, 0, 0, tzinfo=UTC)
    frozen_now = last_sync + timedelta(hours=1)
    row = make_developer(last_sync_at=last_sync, github_login="alice")

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
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
    inputs = GitHubScoreInputs(
        commits_alltime=10,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
        stars_per_repo=(5,),
        forks_received=1,
        followers=7,
        account_created_at=anchor,
    )
    avatar_url = "https://avatars.githubusercontent.com/u/99?v=4"

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
    gh.fetch_score_inputs = AsyncMock(return_value=inputs)
    gh.fetch_public_user_profile = AsyncMock(
        return_value={"id": 99, "login": "bob", "avatar_url": avatar_url}
    )
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=None)
        created_row = None

        def _capture_create(row: object) -> object:
            nonlocal created_row
            created_row = row
            return row

        repo.create = AsyncMock(side_effect=_capture_create)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            out = await svc.sync_for_actor(db, github_id=99, login="bob")

        assert isinstance(out, MeSyncPerformed)
        assert out.first_sync is True
        assert out.progress is None
        assert out.snapshot.login == "bob"
        assert out.snapshot.xp >= 1
        assert created_row is not None
        assert created_row.avatar_url == avatar_url
        repo.create.assert_called_once()
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_stub_row_last_sync_none_runs_full_backfill_not_incremental() -> None:
    """Stub developer from OAuth (last_sync_at=None) must get fetch_score_inputs, not delta-only."""
    fixed_now = datetime(2032, 3, 1, tzinfo=UTC)
    anchor = datetime(2015, 1, 1, tzinfo=UTC)
    inputs = GitHubScoreInputs(
        commits_alltime=2853,
        prs_contributions_alltime=619,
        reviews_alltime=246,
        private_contributions_alltime=0,
        stars_per_repo=(9,),
        forks_received=2,
        followers=30,
        account_created_at=anchor,
    )
    avatar_url = "https://avatars.githubusercontent.com/u/12345?v=4"

    oauth_row = make_developer(
        github_id=12345,
        github_login="ExampleUser",
        last_sync_at=None,
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        created_at=fixed_now - timedelta(days=1),
        updated_at=fixed_now - timedelta(days=1),
    )

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
    gh.fetch_score_inputs = AsyncMock(return_value=inputs)
    gh.fetch_public_user_profile = AsyncMock(
        return_value={
            "id": 12345,
            "login": "ExampleUser",
            "avatar_url": avatar_url,
        }
    )
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=oauth_row)
        repo.create = AsyncMock()
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            out = await svc.sync_for_actor(db, github_id=12345, login="ExampleUser")

        assert isinstance(out, MeSyncPerformed)
        assert out.first_sync is True
        assert out.progress is None
        assert out.snapshot.xp == oauth_row.xp_brut
        gh.fetch_score_inputs.assert_awaited_once_with("ExampleUser", include_org_admin_repos=False)
        gh.contributions_totals_between.assert_not_called()
        repo.create.assert_not_called()
        assert oauth_row.commits_alltime == 2853
        assert oauth_row.prs_contributions_alltime == 619
        assert oauth_row.reviews_alltime == 246
        assert oauth_row.last_sync_at == fixed_now
        assert oauth_row.avatar_url == avatar_url
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
        avatar_url="https://avatars.githubusercontent.com/u/777?v=3",
    )
    new_avatar = "https://avatars.githubusercontent.com/u/777?v=4"

    profile = {
        "id": 777,
        "login": "carol",
        "created_at": "2014-01-01T00:00:00Z",
        "followers": 0,
        "avatar_url": new_avatar,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
    gh.contributions_totals_between = AsyncMock(return_value=(2, 0, 0, 0))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((3, 0, 0), 0))
    gh.commit_breakdown_sum_between = AsyncMock(return_value=2)

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
        assert row.avatar_url == new_avatar
        assert out.progress is not None
        assert out.progress.xp_before == xp_before_incremental
        assert out.progress.xp_after == row.xp_brut == out.snapshot.xp
        assert out.progress.cell_before == get_cell_count(xp_before_incremental)
        assert out.progress.cell_after == out.snapshot.cell_count
        assert out.progress.xp_progress_before == get_xp_progress(xp_before_incremental)
        assert out.progress.xp_progress_after == out.snapshot.xp_progress
        assert row.commits_alltime == 2
        assert row.stars_received_raw == 3
        assert row.owned_non_fork_repos_count == 3
        assert row.avatar_url == new_avatar
        gh.contributions_totals_between.assert_awaited_once_with(
            "carol",
            datetime(2014, 1, 1, tzinfo=UTC),
            frozen_now,
        )
        b = out.progress
        delta_commits = b.breakdown_after.from_commits - b.breakdown_before.from_commits
        delta_prs = b.breakdown_after.from_pull_requests - b.breakdown_before.from_pull_requests
        delta_reviews = b.breakdown_after.from_reviews - b.breakdown_before.from_reviews
        delta_stars = b.breakdown_after.from_stars - b.breakdown_before.from_stars
        delta_forks = b.breakdown_after.from_forks - b.breakdown_before.from_forks
        delta_followers = b.breakdown_after.from_followers - b.breakdown_before.from_followers
        delta_repos = b.breakdown_after.from_repos - b.breakdown_before.from_repos
        delta_tenure = b.breakdown_after.from_tenure - b.breakdown_before.from_tenure
        assert delta_commits == 10
        assert delta_prs == 0
        assert delta_reviews == 0
        assert delta_stars == 150
        assert delta_forks == 0
        assert delta_followers == 0
        assert delta_repos == 40
        assert delta_tenure == 0
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
    gh.with_token = MagicMock(return_value=gh)
    gh.contributions_totals_between = AsyncMock(return_value=(80, 18, 7, 0))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((), 0))
    gh.commit_breakdown_sum_between = AsyncMock(return_value=80)

    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        repo.create = AsyncMock()
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=888, login="eve")

        assert isinstance(out, MeSyncPerformed)
        gh.contributions_totals_between.assert_awaited_once_with(
            "eve",
            datetime(2018, 1, 1, tzinfo=UTC),
            frozen_now,
        )
        assert row.commits_alltime == 80
        assert row.prs_contributions_alltime == 18
        assert row.reviews_alltime == 7
        b = out.progress
        delta_commits = b.breakdown_after.from_commits - b.breakdown_before.from_commits
        delta_prs = b.breakdown_after.from_pull_requests - b.breakdown_before.from_pull_requests
        delta_reviews = b.breakdown_after.from_reviews - b.breakdown_before.from_reviews
        assert delta_commits == 30 * 10
        assert delta_prs == 8 * 30
        assert delta_reviews == 2 * 15


@pytest.mark.asyncio
async def test_sync_for_github_login_resolves_id_from_profile() -> None:
    anchor = datetime(2016, 1, 1, tzinfo=UTC)
    inputs = GitHubScoreInputs(
        commits_alltime=0,
        prs_contributions_alltime=0,
        reviews_alltime=0,
        private_contributions_alltime=0,
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
    gh.with_token = MagicMock(return_value=gh)
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


@pytest.mark.asyncio
async def test_sync_for_actor_uses_stored_token_when_present() -> None:
    """with_token() must be called with the token stored on the developer row."""
    fixed_now = datetime(2035, 1, 1, tzinfo=UTC)
    row = make_developer(
        last_sync_at=None,
        github_login="alice",
        github_id=123,
        github_token="stored_token",
    )

    db = MagicMock()
    db.commit = AsyncMock()

    user_gh = MagicMock()
    user_gh.fetch_score_inputs = AsyncMock(
        return_value=GitHubScoreInputs(
            commits_alltime=0,
            prs_contributions_alltime=0,
            reviews_alltime=0,
            private_contributions_alltime=0,
            stars_per_repo=(),
            forks_received=0,
            followers=0,
            account_created_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    user_gh.fetch_public_user_profile = AsyncMock(
        return_value={"id": 123, "login": "alice", "created_at": "2020-01-01T00:00:00Z"}
    )

    gh = MagicMock()
    gh.with_token = MagicMock(return_value=user_gh)
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            await svc.sync_for_actor(db, github_id=123, login="alice")

        gh.with_token.assert_called_once_with("stored_token")
        user_gh.fetch_score_inputs.assert_awaited_once_with("alice", include_org_admin_repos=True)
        user_gh.fetch_public_user_profile.assert_awaited_once_with("alice")


@pytest.mark.asyncio
async def test_sync_for_actor_uses_no_token_when_row_has_none() -> None:
    """with_token(None) must be called when the row has no stored token."""
    fixed_now = datetime(2035, 1, 1, tzinfo=UTC)
    row = make_developer(last_sync_at=None, github_login="bob", github_id=456, github_token=None)

    db = MagicMock()
    db.commit = AsyncMock()

    user_gh = MagicMock()
    user_gh.fetch_score_inputs = AsyncMock(
        return_value=GitHubScoreInputs(
            commits_alltime=0,
            prs_contributions_alltime=0,
            reviews_alltime=0,
            private_contributions_alltime=0,
            stars_per_repo=(),
            forks_received=0,
            followers=0,
            account_created_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    user_gh.fetch_public_user_profile = AsyncMock(
        return_value={"id": 456, "login": "bob", "created_at": "2020-01-01T00:00:00Z"}
    )

    gh = MagicMock()
    gh.with_token = MagicMock(return_value=user_gh)
    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(fixed_now)):
            await svc.sync_for_actor(db, github_id=456, login="bob")

        # None -> falls back to global token inside GitHubClient
        gh.with_token.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_incremental_sync_flags_commit_farm_and_caps_xp() -> None:
    last_sync = datetime(2030, 5, 1, 12, 0, 0, tzinfo=UTC)
    frozen_now = last_sync + timedelta(hours=8)
    row = make_developer(
        last_sync_at=last_sync,
        github_login="flolep2607",
        github_id=999,
        commits_alltime=26000,
        xp_brut=260000,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    profile = {
        "id": 999,
        "login": "flolep2607",
        "created_at": "2030-01-01T00:00:00Z",
        "followers": 0,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
    gh.contributions_totals_between = AsyncMock(return_value=(26792, 0, 0, 0))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((), 0))
    gh.commit_breakdown_sum_between = AsyncMock(return_value=800)

    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=999, login="flolep2607")

        assert isinstance(out, MeSyncPerformed)
        assert row.commits_alltime == 26792
        assert row.commits_breakdown_sum == 800
        assert row.commits_farm_flagged is True
        assert row.xp_brut == 800 * 10
        assert out.snapshot.github_inputs.commits_alltime == 26792
        assert out.snapshot.xp_breakdown.from_commits == 800 * 10


@pytest.mark.asyncio
async def test_incremental_sync_farm_cleared_keeps_alltime_xp() -> None:
    last_sync = datetime(2030, 5, 1, 12, 0, 0, tzinfo=UTC)
    frozen_now = last_sync + timedelta(hours=8)
    row = make_developer(
        last_sync_at=last_sync,
        github_login="flolep2607",
        github_id=999,
        commits_alltime=26000,
        commits_farm_cleared=True,
        xp_brut=260000,
        account_created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )
    profile = {
        "id": 999,
        "login": "flolep2607",
        "created_at": "2030-01-01T00:00:00Z",
        "followers": 0,
    }

    db = MagicMock()
    db.commit = AsyncMock()
    gh = MagicMock()
    gh.with_token = MagicMock(return_value=gh)
    gh.contributions_totals_between = AsyncMock(return_value=(26792, 0, 0, 0))
    gh.fetch_public_user_profile = AsyncMock(return_value=profile)
    gh.fetch_owner_repo_star_fork_totals = AsyncMock(return_value=((), 0))
    gh.commit_breakdown_sum_between = AsyncMock(return_value=800)

    svc = ScoreSyncService(gh)

    with patch("app.services.score_sync_service.DeveloperRepository") as RepoCls:
        repo = MagicMock()
        repo.get_by_github_id = AsyncMock(return_value=row)
        RepoCls.return_value = repo

        with patch("app.services.score_sync_service.datetime", _patch_now(frozen_now)):
            out = await svc.sync_for_actor(db, github_id=999, login="flolep2607")

        assert row.commits_farm_flagged is True
        assert row.commits_farm_cleared is True
        assert row.xp_brut == 26792 * 10
        assert out.snapshot.xp_breakdown.from_commits == 26792 * 10
