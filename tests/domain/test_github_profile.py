from app.domain.github_profile import github_profile_avatar_url, sync_avatar_url_from_profile
from tests.factories.developer_factory import make_developer


def test_github_profile_avatar_url_returns_trimmed_string() -> None:
    assert github_profile_avatar_url({"avatar_url": "  https://a.test/x  "}) == "https://a.test/x"


def test_github_profile_avatar_url_returns_none_when_missing() -> None:
    assert github_profile_avatar_url({}) is None
    assert github_profile_avatar_url({"avatar_url": "   "}) is None


def test_sync_avatar_url_sets_github_url_when_missing() -> None:
    dev = make_developer(avatar_url=None)
    profile = {"avatar_url": "https://avatars.githubusercontent.com/u/1?v=4"}

    updated = sync_avatar_url_from_profile(dev, profile)

    assert updated is True
    assert dev.avatar_url == profile["avatar_url"]


def test_sync_avatar_url_skips_when_unchanged() -> None:
    url = "https://avatars.githubusercontent.com/u/1?v=4"
    dev = make_developer(avatar_url=url)

    updated = sync_avatar_url_from_profile(dev, {"avatar_url": url})

    assert updated is False


def test_sync_avatar_url_updates_when_github_url_changed() -> None:
    dev = make_developer(avatar_url="https://avatars.githubusercontent.com/u/1?v=3")
    new_url = "https://avatars.githubusercontent.com/u/1?v=4"

    updated = sync_avatar_url_from_profile(dev, {"avatar_url": new_url})

    assert updated is True
    assert dev.avatar_url == new_url
