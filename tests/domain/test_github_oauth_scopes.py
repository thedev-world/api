from app.domain.github_oauth_scopes import (
    BASE_GITHUB_OAUTH_SCOPES,
    GITHUB_ORG_OAUTH_SCOPE,
    github_oauth_scope_string,
    has_github_org_oauth_scope,
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


def test_has_github_org_oauth_scope() -> None:
    assert has_github_org_oauth_scope("read:user,user:email,read:org") is True
    assert has_github_org_oauth_scope("read:user,user:email") is False
    assert has_github_org_oauth_scope(None) is False


def test_base_github_oauth_scopes() -> None:
    assert BASE_GITHUB_OAUTH_SCOPES == frozenset({"read:user", "user:email"})


def test_github_oauth_scope_string() -> None:
    assert github_oauth_scope_string(include_orgs=False) == "read:user user:email"
    assert github_oauth_scope_string(include_orgs=True) == "read:user user:email read:org"
    assert GITHUB_ORG_OAUTH_SCOPE == "read:org"
