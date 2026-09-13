"""v1.0 P1 Playgrounds: SQL / Redis / FastAPI interview sandboxes.

All routes are user-scoped. Sandbox sessions are persisted rows (kind sql /
redis) whose unguessable session key the runner turns into an isolated
PostgreSQL schema and Redis database index; the backend never learns or stores
sandbox contents. Dangerous input is rejected twice — once here (mirror of the
runner policy, app/playground.py) and once inside the runner.
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .deps import current_user
from .models import PlaygroundSession, User
from .timeutil import utc_now
from .observability import audit
from .playground import (
    PLAYGROUND_KINDS,
    SAMPLE_SNIPPETS,
    SandboxPolicyError,
    redis_guard,
    sql_guard,
)
from .schemas import (
    PlaygroundFastApiRequest,
    PlaygroundRedisRequest,
    PlaygroundResetRequest,
    PlaygroundSessionCreate,
    PlaygroundSqlRequest,
)

router = APIRouter()

RUNNER_TIMEOUT_SECONDS = 15.0


async def _runner_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Single choke point for runner calls — tests monkeypatch this."""
    async with httpx.AsyncClient(timeout=RUNNER_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{settings.runner_url}{path}", json=payload)
        response.raise_for_status()
        return response.json()


async def _owned_session(
    db: AsyncSession, user: User, session_id: int, kind: str
) -> PlaygroundSession:
    session = await db.scalar(
        select(PlaygroundSession).where(
            PlaygroundSession.id == session_id, PlaygroundSession.user_id == user.id
        )
    )
    if not session:
        # 404 both for missing and foreign sessions: session ids of other
        # users are indistinguishable from non-existent ones.
        raise HTTPException(404, "Playground session not found")
    if session.kind != kind:
        raise HTTPException(400, f"This session is a {session.kind} playground session")
    if session.expires_at < utc_now():
        raise HTTPException(410, "Playground session expired; create a new one")
    session.last_used_at = utc_now()
    await db.commit()
    return session


@router.get("/api/playground/meta")
async def playground_meta() -> dict[str, Any]:
    return {
        "kinds": list(PLAYGROUND_KINDS) + ["fastapi"],
        "limits": {
            "sql_max_chars": settings.playground_sql_max_chars,
            "redis_max_chars": settings.playground_redis_max_chars,
            "fastapi_max_chars": settings.playground_fastapi_max_chars,
            "session_ttl_hours": settings.playground_session_ttl_hours,
        },
        "policy": {
            "sql": "每批 SQL 在会话专属 schema 中原子执行（任一语句失败整批回滚）；DROP DATABASE / CREATE ROLE / pg_sleep 等危险语句被拦截。",
            "redis": "命令在会话专属 DB index 中执行；FLUSHALL / CONFIG / EVAL / SELECT 等危险命令被拦截。",
            "fastapi": "用户应用运行在独立子进程（资源限制 + 超时），请求经 TestClient 发送；不会触碰主服务。",
        },
        "samples": SAMPLE_SNIPPETS,
    }


@router.post("/api/playground/sessions")
async def create_playground_session(
    payload: PlaygroundSessionCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Housekeeping: expired sessions are inert (the runner's sandbox state
    # expires on its own TTL), drop them lazily like oauth_states.
    await db.execute(
        delete(PlaygroundSession).where(PlaygroundSession.expires_at < utc_now() - timedelta(hours=1))
    )
    session = PlaygroundSession(
        session_key=secrets.token_hex(16),
        user_id=user.id,
        kind=payload.kind,
        expires_at=utc_now() + timedelta(hours=settings.playground_session_ttl_hours),
    )
    db.add(session)
    await db.commit()
    audit("playground.session_created", user_id=user.id, username=user.username, kind=payload.kind)
    return {
        "session_id": session.id,
        "kind": session.kind,
        "expires_in": settings.playground_session_ttl_hours * 3600,
    }


@router.post("/api/playground/sql")
async def run_playground_sql(
    payload: PlaygroundSqlRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _owned_session(db, user, payload.session_id, "sql")
    try:
        sql_guard(payload.sql)
    except SandboxPolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        return await _runner_post("/pg/sql", {"session_key": session.session_key, "sql": payload.sql})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sandbox unavailable: {exc}") from exc


@router.post("/api/playground/redis")
async def run_playground_redis(
    payload: PlaygroundRedisRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _owned_session(db, user, payload.session_id, "redis")
    try:
        redis_guard(payload.command)
    except SandboxPolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        return await _runner_post("/pg/redis", {"session_key": session.session_key, "command": payload.command})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sandbox unavailable: {exc}") from exc


@router.post("/api/playground/fastapi")
async def run_playground_fastapi(
    payload: PlaygroundFastApiRequest, user: User = Depends(current_user)
) -> dict[str, Any]:
    if len(payload.code) > settings.playground_fastapi_max_chars:
        raise HTTPException(400, f"code exceeds {settings.playground_fastapi_max_chars} characters")
    try:
        return await _runner_post(
            "/pg/fastapi",
            {"code": payload.code, "method": payload.method, "path": payload.path, "body": payload.body},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sandbox unavailable: {exc}") from exc


@router.post("/api/playground/reset")
async def reset_playground(
    payload: PlaygroundResetRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await db.scalar(
        select(PlaygroundSession).where(
            PlaygroundSession.id == payload.session_id, PlaygroundSession.user_id == user.id
        )
    )
    if not session:
        raise HTTPException(404, "Playground session not found")
    try:
        result = await _runner_post("/pg/reset", {"session_key": session.session_key})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Sandbox unavailable: {exc}") from exc
    return {"session_id": session.id, "kind": session.kind, **result}
