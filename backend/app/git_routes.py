"""v1.0 Git provider integration routes: OAuth authorize/callback for
GitHub and Gitee, encrypted per-user token connections, provider repository
listing and disconnect. All routes are user-scoped; provider tokens are
never returned and never logged."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from .db import get_db
from .timeutil import utc_now
from .deps import current_user
from .git_oauth import (
    PROVIDERS,
    GitProviderError,
    build_authorize_url,
    decrypt_token,
    encrypt_token,
    exchange_code,
    fetch_provider_user,
    list_provider_repos,
    provider_is_configured,
)
from .models import GitConnection, OAuthState, User
from .observability import audit
from .schemas import GitCallbackRequest

router = APIRouter()

STATE_TTL_MINUTES = 10


def _require_provider(provider: str) -> str:
    normalized = provider.lower().strip()
    if normalized not in PROVIDERS:
        raise HTTPException(404, "Unsupported git provider")
    return normalized


def _require_configured(provider: str) -> None:
    if not provider_is_configured(provider):
        raise HTTPException(
            400,
            f"{provider} OAuth is not configured: set {provider.upper()}_CLIENT_ID and "
            f"{provider.upper()}_CLIENT_SECRET in the backend environment",
        )


async def _owned_connection(db: AsyncSession, user: User, provider: str) -> GitConnection:
    connection = await db.scalar(
        select(GitConnection).where(GitConnection.user_id == user.id, GitConnection.provider == provider)
    )
    if not connection:
        raise HTTPException(404, f"No connected {provider} account; authorize the provider first")
    return connection


async def _connection_token(db: AsyncSession, user: User, provider: str) -> str:
    connection = await _owned_connection(db, user, provider)
    if not connection.access_token_encrypted:
        raise HTTPException(400, f"The stored {provider} token is empty; disconnect and re-authorize")
    try:
        return decrypt_token(connection.access_token_encrypted)
    except ValueError as exc:
        raise HTTPException(
            400,
            f"The stored {provider} token cannot be decrypted (encryption key changed); "
            "disconnect the provider and authorize it again",
        ) from exc


@router.get("/api/git/providers")
async def git_provider_status(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    connections = {
        connection.provider: connection
        for connection in (
            await db.scalars(select(GitConnection).where(GitConnection.user_id == user.id))
        ).all()
    }
    return [
        {
            "provider": provider,
            "configured": provider_is_configured(provider),
            "connected": provider in connections,
            "login": connections[provider].provider_login if provider in connections else "",
            "scopes": connections[provider].scopes if provider in connections else "",
            "connected_at": connections[provider].created_at.isoformat() if provider in connections else None,
        }
        for provider in sorted(PROVIDERS)
    ]


@router.post("/api/git/{provider}/authorize")
async def start_git_authorize(
    provider: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    provider = _require_provider(provider)
    _require_configured(provider)
    # Housekeeping: drop consumed/expired states older than an hour.
    await db.execute(delete(OAuthState).where(OAuthState.expires_at < utc_now() - timedelta(hours=1)))
    state_value = secrets.token_urlsafe(32)
    db.add(
        OAuthState(
            state=state_value,
            user_id=user.id,
            provider=provider,
            expires_at=utc_now() + timedelta(minutes=STATE_TTL_MINUTES),
        )
    )
    await db.commit()
    audit("git.authorize_started", user_id=user.id, username=user.username, provider=provider)
    return {
        "provider": provider,
        "authorize_url": build_authorize_url(provider, state_value),
        "state": state_value,
        "expires_in": STATE_TTL_MINUTES * 60,
    }


@router.post("/api/git/callback")
async def git_callback(
    payload: GitCallbackRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    state_row = await db.scalar(select(OAuthState).where(OAuthState.state == payload.state))
    if not state_row or state_row.user_id != user.id or state_row.provider not in PROVIDERS:
        raise HTTPException(400, "Unknown OAuth state; start the authorization again from the projects page")
    if state_row.consumed_at is not None:
        raise HTTPException(400, "This authorization has already been completed; start a new one to re-authorize")
    if state_row.expires_at < utc_now():
        raise HTTPException(400, "OAuth state expired; start the authorization again")
    provider = state_row.provider
    _require_configured(provider)

    state_row.consumed_at = utc_now()
    await db.commit()

    try:
        token_data = await exchange_code(provider, payload.code)
        access_token = str(token_data["access_token"])
        scopes = str(token_data.get("scope") or "")
        profile = await fetch_provider_user(provider, access_token)
    except GitProviderError as exc:
        raise HTTPException(502, f"{provider} authorization failed: {exc}") from exc

    connection = await db.scalar(
        select(GitConnection).where(GitConnection.user_id == user.id, GitConnection.provider == provider)
    )
    if connection:
        connection.provider_login = profile["login"]
        connection.provider_user_id = profile["id"]
        connection.access_token_encrypted = encrypt_token(access_token)
        connection.scopes = scopes[:255]
        connection.updated_at = utc_now()
    else:
        connection = GitConnection(
            user_id=user.id,
            provider=provider,
            provider_login=profile["login"],
            provider_user_id=profile["id"],
            access_token_encrypted=encrypt_token(access_token),
            scopes=scopes[:255],
        )
        db.add(connection)
    await db.commit()
    # Metadata only — the OAuth code, access token and scopes stay out of logs.
    audit("git.connected", user_id=user.id, username=user.username, provider=provider, login=connection.provider_login)
    return {
        "provider": provider,
        "connected": True,
        "login": connection.provider_login,
        "scopes": connection.scopes,
        "connected_at": connection.created_at.isoformat(),
    }


@router.delete("/api/git/{provider}")
async def disconnect_git_provider(
    provider: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    provider = _require_provider(provider)
    connection = await _owned_connection(db, user, provider)
    await db.delete(connection)
    await db.commit()
    audit("git.disconnected", user_id=user.id, username=user.username, provider=provider)
    return {"provider": provider, "connected": False}


@router.get("/api/git/{provider}/repos")
async def git_provider_repositories(
    provider: str,
    visibility: str = Query(default="all", pattern="^(all|public|private)$"),
    page: int = Query(default=1, ge=1, le=50),
    per_page: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    provider = _require_provider(provider)
    access_token = await _connection_token(db, user, provider)
    try:
        repos = await list_provider_repos(
            provider, access_token, visibility=visibility, page=page, per_page=per_page
        )
    except GitProviderError as exc:
        raise HTTPException(502, f"{provider} repository listing failed: {exc}") from exc
    return {"provider": provider, "visibility": visibility, "page": page, "per_page": per_page, "repos": repos}
