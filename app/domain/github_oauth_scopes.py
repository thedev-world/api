from __future__ import annotations

BASE_GITHUB_OAUTH_SCOPES: frozenset[str] = frozenset({"read:user", "user:email"})
GITHUB_ORG_OAUTH_SCOPE = "read:org"


def parse_github_oauth_scopes(scope: str | None) -> frozenset[str]:
    if not scope:
        return frozenset()
    return frozenset(part.strip() for part in scope.split(",") if part.strip())


def has_github_org_oauth_scope(scope: str | None) -> bool:
    return GITHUB_ORG_OAUTH_SCOPE in parse_github_oauth_scopes(scope)


def is_oauth_scope_downgrade(stored: str | None, incoming: str | None) -> bool:
    return parse_github_oauth_scopes(incoming) < parse_github_oauth_scopes(stored)


def github_oauth_scope_string(*, include_orgs: bool) -> str:
    scopes = "read:user user:email"
    if include_orgs:
        scopes = f"{scopes} {GITHUB_ORG_OAUTH_SCOPE}"
    return scopes
