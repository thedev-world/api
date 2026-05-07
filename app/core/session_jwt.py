from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from app.config import Settings


def issue_session_token(*, developer_id: UUID, settings: Settings) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(developer_id),
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_expires_seconds),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_session_token(token: str, settings: Settings) -> dict[str, object]:
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
