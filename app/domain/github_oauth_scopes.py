from __future__ import annotations

REQUIRED_GITHUB_OAUTH_SCOPES: frozenset[str] = frozenset({"read:org"})
GITHUB_REAUTH_REQUIRED_DETAIL = "github_reauth_required"


def parse_github_oauth_scopes(scope: str | None) -> frozenset[str]:
    if not scope:
        return frozenset()
    return frozenset(part.strip() for part in scope.split(",") if part.strip())


def has_required_github_oauth_scopes(scope: str | None) -> bool:
    return REQUIRED_GITHUB_OAUTH_SCOPES <= parse_github_oauth_scopes(scope)
