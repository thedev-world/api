from app.domain.github_oauth_scopes import (
    GITHUB_REAUTH_REQUIRED_DETAIL,
    has_required_github_oauth_scopes,
    parse_github_oauth_scopes,
)


def test_parse_github_oauth_scopes_empty() -> None:
    assert parse_github_oauth_scopes(None) == frozenset()
    assert parse_github_oauth_scopes("") == frozenset()
    assert parse_github_oauth_scopes("  ,  ") == frozenset()


def test_parse_github_oauth_scopes_splits_commas() -> None:
    assert parse_github_oauth_scopes("read:user,user:email,read:org") == frozenset(
        {"read:user", "user:email", "read:org"}
    )


def test_has_required_github_oauth_scopes() -> None:
    assert has_required_github_oauth_scopes("read:user,user:email,read:org") is True
    assert has_required_github_oauth_scopes("read:user,user:email") is False
    assert has_required_github_oauth_scopes(None) is False


def test_github_reauth_required_detail_is_stable() -> None:
    assert GITHUB_REAUTH_REQUIRED_DETAIL == "github_reauth_required"
