from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

import jwt
from app.config import Settings, get_settings
from app.core.session_jwt import decode_session_token
from app.database import get_db
from app.models.developer import Developer
from app.repositories.developer import DeveloperRepository
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

logger = logging.getLogger(__name__)


async def get_current_developer(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Developer:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = decode_session_token(token, settings)
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session",
            )
        dev_id = UUID(sub)
    except HTTPException:
        raise
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError) as exc:
        logger.debug("Session decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc

    repo = DeveloperRepository(db)
    dev = await repo.get_by_id(dev_id)
    if dev is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return dev
