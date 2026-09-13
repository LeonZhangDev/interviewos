from __future__ import annotations

from datetime import timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import bearer_payload
from .db import get_db
from .models import User


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    payload = getattr(request.state, "auth", None)
    if payload is None:
        payload = bearer_payload(request)
    user = await db.scalar(select(User).where(User.username == str(payload["sub"])))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    issued_at = int(payload.get("iat", 0))
    valid_after = user.tokens_valid_after.replace(tzinfo=timezone.utc).timestamp()
    if issued_at < valid_after:
        raise HTTPException(status_code=401, detail="Token was revoked; please sign in again")
    return user
