from __future__ import annotations

import csv
import io
import json
import uuid
from collections import Counter
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (
    bearer_subject,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from .code_intel import build_architecture
from .config import settings
from .db import get_db
from .timeutil import utc_now
from .deps import current_user
from .fsrs import elapsed_days, legacy_state, retrievability
from .llm import llm
from .observability import audit
from .models import (
    AnswerVersion,
    InterviewRecording,
    InterviewSession,
    InterviewTurn,
    KnowledgeNode,
    Mastery,
    PrerequisiteEdge,
    Question,
    QuestionImportBatch,
    RefreshToken,
    RepoFile,
    Repository,
    SystemDesignCanvas,
    User,
)
from .question_cms import find_duplicates, slugify as _slugify
from .schemas import (
    CanvasSave,
    ChangePasswordRequest,
    LoginCreate,
    LogoutRequest,
    QuestionImportCreate,
    RefreshRequest,
    RegisterCreate,
    ResumeGenerateCreate,
    TranscriptSave,
)
from .seed import bootstrap_user_workspace

router = APIRouter()


def _subject(request: Request) -> str:
    return bearer_subject(request)


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name or user.username,
        "created_at": user.created_at.isoformat(),
    }


async def _issue_refresh_token(db: AsyncSession, user: User) -> str:
    token = create_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(token),
        expires_at=utc_now() + timedelta(days=settings.auth_refresh_days),
    ))
    await db.commit()
    return token


@router.post("/api/auth/register")
async def register(payload: RegisterCreate, db: AsyncSession = Depends(get_db)) -> dict:
    identity = payload.email.strip().lower()
    if "@" not in identity or "." not in identity.rsplit("@", 1)[-1]:
        raise HTTPException(422, "Please enter a valid email address")
    username = payload.username.strip()
    exists = await db.scalar(select(User).where(or_(User.username == username, User.email == identity)))
    if exists:
        raise HTTPException(409, "Username or email already exists")
    user = User(
        username=username,
        email=identity,
        display_name=payload.display_name.strip() or username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await bootstrap_user_workspace(db, user)
    refresh_token = await _issue_refresh_token(db, user)
    audit("auth.register", user_id=user.id, username=user.username)
    return {
        "access_token": create_access_token(user.username),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.post("/api/auth/login")
async def login(payload: LoginCreate, db: AsyncSession = Depends(get_db)) -> dict:
    identity = payload.identity.strip()
    user = await db.scalar(select(User).where(or_(User.username == identity, User.email == identity.lower())))
    if not user or not verify_password(payload.password, user.password_hash):
        # Metadata only: the attempted identity, never the password.
        audit("auth.login_failed", username=identity)
        raise HTTPException(401, "Invalid username/email or password")
    refresh_token = await _issue_refresh_token(db, user)
    audit("auth.login", user_id=user.id, username=user.username)
    return {
        "access_token": create_access_token(user.username),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.post("/api/auth/refresh")
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    token_hash = hash_refresh_token(payload.refresh_token)
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    now = utc_now()
    if not row or row.revoked_at is not None or row.expires_at <= now:
        raise HTTPException(401, "Invalid or expired refresh token")
    user = await db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "User no longer exists")
    # Rotation: every refresh revokes the presented token and issues a new one.
    row.revoked_at = now
    new_refresh = create_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(new_refresh),
        expires_at=now + timedelta(days=settings.auth_refresh_days),
    ))
    await db.commit()
    return {
        "access_token": create_access_token(user.username),
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.post("/api/auth/logout")
async def logout(payload: LogoutRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    row = None
    if payload.refresh_token:
        row = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(payload.refresh_token))
        )
        if row and row.revoked_at is None:
            row.revoked_at = utc_now()
            await db.commit()
            audit("auth.logout", user_id=row.user_id, all_devices=False)
    if payload.all_devices:
        user = None
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            try:
                subject = str(decode_access_token(header[7:].strip())["sub"])
            except HTTPException:
                subject = ""
            if subject:
                user = await db.scalar(select(User).where(User.username == subject))
        if user is None and row is not None:
            user = await db.get(User, row.user_id)
        if user:
            boundary = utc_now()
            user.tokens_valid_after = boundary
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=boundary)
            )
            await db.commit()
            audit("auth.logout", user_id=user.id, username=user.username, all_devices=True)
    return {"status": "logged_out"}


@router.post("/api/auth/change-password")
async def change_password(payload: ChangePasswordRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    # Invalidate every outstanding access token and refresh token.
    boundary = utc_now()
    user.tokens_valid_after = boundary
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=boundary)
    )
    await db.commit()
    refresh_token = await _issue_refresh_token(db, user)
    # +1s keeps the fresh access token above the revocation watermark even
    # when DB and token clocks share the same second. The datetime must be
    # timezone-aware: naive datetimes are read as local time by .timestamp().
    access_token = create_access_token(
        user.username,
        issued_at=(boundary + timedelta(seconds=1)).replace(tzinfo=timezone.utc),
    )
    audit("auth.change_password", user_id=user.id, username=user.username)
    return {
        "status": "password_changed",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.get("/api/auth/me")
async def me(user: User = Depends(current_user)) -> dict:
    return _user_payload(user)


def _safe_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


@router.get("/api/knowledge-graph")
async def knowledge_graph(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    questions = (await db.scalars(select(Question).order_by(Question.category, Question.id).limit(180))).all()
    mastery = {x.topic: x for x in (await db.scalars(select(Mastery).where(Mastery.user_id == user.id))).all()}
    repos = (await db.scalars(
        select(Repository).where(Repository.user_id == user.id).order_by(Repository.synced_at.desc()).limit(12)
    )).all()

    nodes: list[dict] = []
    edges: list[dict] = []
    categories = sorted({q.category for q in questions})
    category_ids: dict[str, str] = {}
    for category in categories:
        nid = f"cat:{category}"
        category_ids[category] = nid
        possible = [m for name, m in mastery.items() if category.lower() in name.lower() or name.lower() in category.lower()]
        score = round(sum(m.score for m in possible) / len(possible), 1) if possible else None
        nodes.append({"id": nid, "label": category, "kind": "category", "score": score})

    for q in questions:
        qid = f"q:{q.id}"
        nodes.append({"id": qid, "label": q.title, "kind": "question", "category": q.category, "difficulty": q.difficulty})
        edges.append({"id": f"e:{category_ids[q.category]}:{qid}", "source": category_ids[q.category], "target": qid, "label": "contains"})
        if q.project_link:
            project_id = f"project:{q.project_link}"
            if not any(n["id"] == project_id for n in nodes):
                nodes.append({"id": project_id, "label": q.project_link, "kind": "project"})
            edges.append({"id": f"e:{project_id}:{qid}", "source": project_id, "target": qid, "label": "asks"})

    topic_counter: Counter[str] = Counter()
    for repo in repos:
        repo_id = f"repo:{repo.id}"
        nodes.append({"id": repo_id, "label": repo.name, "kind": "repository", "provider": repo.provider})
        summary = _safe_json(repo.summary, {})
        for topic, count in (summary.get("topics") or [])[:10]:
            topic = str(topic)
            topic_counter[topic] += int(count)
            topic_id = f"topic:{topic}"
            if not any(n["id"] == topic_id for n in nodes):
                score = next((m.score for name, m in mastery.items() if topic.lower() in name.lower() or name.lower() in topic.lower()), None)
                nodes.append({"id": topic_id, "label": topic, "kind": "topic", "score": score})
            edges.append({"id": f"e:{repo_id}:{topic_id}", "source": repo_id, "target": topic_id, "label": "uses"})
            for category, cid in category_ids.items():
                if topic.lower() in category.lower() or category.lower() in topic.lower():
                    edges.append({"id": f"e:{topic_id}:{cid}", "source": topic_id, "target": cid, "label": "relates"})

    return {
        "nodes": nodes[:320],
        "edges": edges[:520],
        "stats": {
            "questions": len(questions),
            "categories": len(categories),
            "repositories": len(repos),
            "weak_topics": sum(1 for m in mastery.values() if m.score < 70),
        },
    }


PREREQ_MASTERY_THRESHOLD = 70.0


def _assign_layers(node_slugs: set[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """Kahn-style layering: a node's layer is one past its deepest incoming
    edge. Raises on a cyclic seed graph instead of silently looping."""
    indegree = {slug: 0 for slug in node_slugs}
    adjacency: dict[str, list[str]] = {slug: [] for slug in node_slugs}
    for from_slug, to_slug in edges:
        adjacency[from_slug].append(to_slug)
        indegree[to_slug] += 1
    layer: dict[str, int] = {slug: 0 for slug, degree in indegree.items() if degree == 0}
    frontier = list(layer)
    while frontier:
        next_frontier: list[str] = []
        for slug in frontier:
            for target in adjacency[slug]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    layer[target] = layer[slug] + 1
                    next_frontier.append(target)
        frontier = next_frontier
    if len(layer) != len(node_slugs):
        cyclic = sorted(set(node_slugs) - set(layer))
        raise HTTPException(500, f"prerequisite graph has a cycle: {cyclic}")
    return layer


async def _prerequisite_data(db: AsyncSession, user: User) -> dict:
    """Shared graph structure + the current user's chain-level mastery view."""
    node_rows = (await db.scalars(select(KnowledgeNode).order_by(KnowledgeNode.chain, KnowledgeNode.position))).all()
    edge_rows = (await db.scalars(select(PrerequisiteEdge))).all()
    if not node_rows:
        raise HTTPException(503, "prerequisite graph not seeded")

    now = utc_now()
    mastery = {m.topic: m for m in (await db.scalars(select(Mastery).where(Mastery.user_id == user.id))).all()}
    edges = [(e.from_slug, e.to_slug) for e in edge_rows]
    layers = _assign_layers({n.slug for n in node_rows}, edges)

    node_by_slug = {n.slug: n for n in node_rows}
    passed_chain = {
        chain: chain in mastery and mastery[chain].score >= PREREQ_MASTERY_THRESHOLD
        for chain in {n.chain for n in node_rows}
    }
    incoming: dict[str, list[str]] = {n.slug: [] for n in node_rows}
    for from_slug, to_slug in edges:
        incoming[to_slug].append(from_slug)

    nodes_payload = []
    for node in node_rows:
        weak_prereqs = [
            node_by_slug[p].label for p in incoming[node.slug]
            if not passed_chain.get(node_by_slug[p].chain, False)
        ]
        nodes_payload.append({
            "slug": node.slug,
            "label": node.label,
            "chain": node.chain,
            "description": node.description,
            "position": node.position,
            "layer": layers[node.slug],
            "blocked": bool(weak_prereqs),
            "weak_prereqs": weak_prereqs,
        })

    edges_payload = [
        {
            "from_slug": f,
            "to_slug": t,
            "cross_chain": node_by_slug[f].chain != node_by_slug[t].chain,
        }
        for f, t in edges
    ]

    chain_mastery = {}
    for chain in {n.chain for n in node_rows}:
        m = mastery.get(chain)
        if m is None:
            chain_mastery[chain] = {"score": None, "retrievability": None, "due": None, "reps": 0, "lapses": 0}
            continue
        stability, difficulty = (
            (m.stability, m.difficulty) if m.stability > 0 and m.difficulty > 0
            else legacy_state(m.score, m.interval_days)
        )
        r = retrievability(elapsed_days(m.last_review_at, now), stability)
        chain_mastery[chain] = {
            "score": m.score,
            "retrievability": round(r, 4),
            "due": m.due_at <= now,
            "reps": m.reps,
            "lapses": m.lapses,
        }

    return {
        "nodes": nodes_payload,
        "edges": edges_payload,
        "chain_mastery": chain_mastery,
        "threshold": PREREQ_MASTERY_THRESHOLD,
    }


@router.get("/api/knowledge/prerequisites")
async def prerequisite_graph(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Shared prerequisite graph (structure identical for everyone) overlaid
    with the current user's chain-level mastery and blocked-node state."""
    return await _prerequisite_data(db, user)


@router.get("/api/knowledge/prerequisites/recommendations")
async def prerequisite_recommendations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Explainable unlock suggestions: every chain below the mastery
    threshold is a candidate; priority = how many nodes it blocks (direct
    prerequisites elsewhere in the graph), then by how far below threshold."""
    data = await _prerequisite_data(db, user)
    nodes = data["nodes"]
    chain_mastery = data["chain_mastery"]

    node_index = {n["slug"]: n for n in nodes}
    prereqs_of = {n["slug"]: [
        f for f, t in ((e["from_slug"], e["to_slug"]) for e in data["edges"]) if t == n["slug"]
    ] for n in nodes}
    blocked_by_chain: dict[str, int] = {}
    for node in nodes:
        blocking_chains = {
            node_index[p]["chain"]
            for p in prereqs_of[node["slug"]]
            if chain_mastery.get(node_index[p]["chain"], {}).get("score") is None
            or chain_mastery[node_index[p]["chain"]]["score"] < data["threshold"]
        }
        for chain in blocking_chains:
            blocked_by_chain[chain] = blocked_by_chain.get(chain, 0) + 1

    chains = sorted({n["chain"] for n in nodes})
    result = []
    for chain in chains:
        info = chain_mastery.get(chain, {})
        score = info.get("score")
        if score is not None and score >= data["threshold"]:
            continue
        chain_nodes = [n for n in nodes if n["chain"] == chain]
        first_steps = [n["label"] for n in chain_nodes[:2]]
        retrievability_value = info.get("retrievability")
        parts = [
            f"掌握度 {round(score)}%（低于 {round(data['threshold'])}% 达标线）" if score is not None
            else "还没有这条链的复习记录"
        ]
        if retrievability_value is not None:
            parts.append(f"FSRS 保持率 {round(retrievability_value * 100)}%")
        if info.get("due"):
            parts.append("已到复习时间")
        blocked = blocked_by_chain.get(chain, 0)
        if blocked:
            parts.append(f"它在图上阻塞 {blocked} 个下游知识点")
        result.append({
            "chain": chain,
            "score": score,
            "retrievability": retrievability_value,
            "due": bool(info.get("due")),
            "blocked_count": blocked,
            "first_steps": first_steps,
            "reason": "；".join(parts),
        })

    result.sort(key=lambda r: (-r["blocked_count"], r["score"] if r["score"] is not None else 0))
    return result


@router.get("/api/search")
async def unified_search(
    q: str = Query(default="", max_length=100),
    per_group: int = Query(default=5, ge=1, le=20),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unified search across shared content (questions, knowledge nodes) and
    the current user's private records (repository files, answer versions,
    interview turns). Matching is lower() LIKE substring search rather than
    to_tsvector: the seed content is Chinese-heavy (an English FTS tokenizer
    would match nothing) and the offline test suite runs on SQLite, where
    tsvector does not exist."""
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(422, "Search query must be at least 2 characters")
    # Hyphens in the query become single-char wildcards, so "xenon-marker"
    # matches both literal "xenon-marker" prose and "xenon_marker.py" code
    # identifiers (LIKE "_" matches any one character, either separator).
    pattern = f"%{term.replace('-', '_')}%"

    question_rows = (await db.scalars(
        select(Question)
        .where(
            Question.archived == 0,
            or_(Question.title.ilike(pattern), Question.category.ilike(pattern), Question.answer.ilike(pattern)),
        )
        .order_by(Question.category, Question.id)
        .limit(per_group)
    )).all()
    questions_group = [{
        "id": row.id,
        "title": row.title,
        "subtitle": f"{row.category} · 难度 {row.difficulty}",
        "question_id": row.id,
    } for row in question_rows]

    node_rows = (await db.scalars(
        select(KnowledgeNode)
        .where(or_(
            KnowledgeNode.label.ilike(pattern),
            KnowledgeNode.chain.ilike(pattern),
            KnowledgeNode.description.ilike(pattern),
        ))
        .order_by(KnowledgeNode.chain, KnowledgeNode.position)
        .limit(per_group)
    )).all()
    nodes_group = [{
        "id": row.slug,
        "title": row.label,
        "subtitle": f"{row.chain} · 知识点",
    } for row in node_rows]

    file_rows = (await db.execute(
        select(RepoFile, Repository.name)
        .join(Repository, RepoFile.repository_id == Repository.id)
        .where(
            Repository.user_id == user.id,
            or_(RepoFile.path.ilike(pattern), RepoFile.symbols.ilike(pattern)),
        )
        .order_by(Repository.id, RepoFile.path)
        .limit(per_group)
    )).all()
    files_group = [{
        "id": file.id,
        "title": file.path,
        "subtitle": f"{repo_name} · {file.language}",
        "repo_id": file.repository_id,
    } for file, repo_name in file_rows]

    answer_rows = (await db.execute(
        select(AnswerVersion, Question.title)
        .join(Question, AnswerVersion.question_id == Question.id)
        .where(AnswerVersion.user_id == user.id, AnswerVersion.content.ilike(pattern))
        .order_by(AnswerVersion.created_at.desc(), AnswerVersion.id.desc())
        .limit(per_group)
    )).all()
    answers_group = [{
        "id": version.id,
        "title": title,
        "subtitle": f"我的答案 · 得分 {round(version.score)} · {version.created_at:%Y-%m-%d}",
        "question_id": version.question_id,
    } for version, title in answer_rows]

    turn_rows = (await db.execute(
        select(InterviewTurn, InterviewSession.role)
        .join(InterviewSession, InterviewTurn.session_id == InterviewSession.id)
        .where(
            InterviewTurn.user_id == user.id,
            or_(InterviewTurn.interviewer_prompt.ilike(pattern), InterviewTurn.user_answer.ilike(pattern)),
        )
        .order_by(InterviewTurn.created_at.desc(), InterviewTurn.id.desc())
        .limit(per_group)
    )).all()
    turns_group = [{
        "id": turn.id,
        "title": turn.interviewer_prompt[:60] + ("…" if len(turn.interviewer_prompt) > 60 else ""),
        "subtitle": f"{role} · 面试轮次 · 得分 {round(turn.score)}",
        "session_id": turn.session_id,
    } for turn, role in turn_rows]

    groups = [
        {"type": "question", "label": "面试题", "items": questions_group},
        {"type": "knowledge_node", "label": "知识点", "items": nodes_group},
        {"type": "repo_file", "label": "仓库文件", "items": files_group},
        {"type": "answer_version", "label": "我的答案", "items": answers_group},
        {"type": "interview_turn", "label": "面试轮次", "items": turns_group},
    ]
    return {"query": term, "groups": groups, "total": sum(len(g["items"]) for g in groups)}


@router.put("/api/system-design/canvas")
async def save_canvas(payload: CanvasSave, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    owner = _subject(request)
    item = await db.scalar(select(SystemDesignCanvas).where(SystemDesignCanvas.owner == owner, SystemDesignCanvas.case_id == payload.case_id))
    if not item:
        item = SystemDesignCanvas(owner=owner, case_id=payload.case_id)
        db.add(item)
    item.title = payload.title
    item.nodes_json = json.dumps(payload.nodes, ensure_ascii=False)
    item.edges_json = json.dumps(payload.edges, ensure_ascii=False)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "case_id": item.case_id, "title": item.title, "nodes": payload.nodes, "edges": payload.edges, "updated_at": item.updated_at.isoformat()}


@router.get("/api/system-design/canvas/{case_id}")
async def get_canvas(case_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    owner = _subject(request)
    item = await db.scalar(select(SystemDesignCanvas).where(SystemDesignCanvas.owner == owner, SystemDesignCanvas.case_id == case_id))
    if not item:
        return {"case_id": case_id, "title": "", "nodes": [], "edges": [], "updated_at": None}
    return {
        "id": item.id,
        "case_id": item.case_id,
        "title": item.title,
        "nodes": _safe_json(item.nodes_json, []),
        "edges": _safe_json(item.edges_json, []),
        "updated_at": item.updated_at.isoformat(),
    }


@router.post("/api/interviews/{session_id}/recording")
async def upload_recording(session_id: int, user: User = Depends(current_user), request: Request = None, db: AsyncSession = Depends(get_db)) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Interview session not found")
    owner = user.username
    body = await request.body()
    if not body:
        raise HTTPException(422, "Recording body is empty")
    if len(body) > 30 * 1024 * 1024:
        raise HTTPException(413, "Recording is larger than 30 MB")
    mime = request.headers.get("content-type", "audio/webm").split(";", 1)[0].strip().lower()
    extension = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/wav": ".wav"}.get(mime, ".bin")
    directory = Path(settings.recordings_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"session-{session_id}-{uuid.uuid4().hex}{extension}"
    path = directory / filename
    path.write_bytes(body)
    item = InterviewRecording(session_id=session_id, owner=owner, mime_type=mime, file_path=str(path))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "session_id": session_id, "mime_type": mime, "size": len(body), "created_at": item.created_at.isoformat()}


@router.put("/api/interviews/{session_id}/recordings/{recording_id}/transcript")
async def save_transcript(session_id: int, recording_id: int, payload: TranscriptSave, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Recording not found")
    item = await db.get(InterviewRecording, recording_id)
    if not item or item.session_id != session_id or item.owner != user.username:
        raise HTTPException(404, "Recording not found")
    item.transcript = payload.transcript.strip()
    item.duration_ms = payload.duration_ms
    await db.commit()
    return {"id": item.id, "transcript": item.transcript, "duration_ms": item.duration_ms}


@router.get("/api/interviews/{session_id}/recordings")
async def list_recordings(session_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    session = await db.get(InterviewSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Interview session not found")
    items = (await db.scalars(select(InterviewRecording).where(InterviewRecording.session_id == session_id, InterviewRecording.owner == user.username).order_by(InterviewRecording.id.desc()))).all()
    return [{"id": x.id, "mime_type": x.mime_type, "transcript": x.transcript, "duration_ms": x.duration_ms, "created_at": x.created_at.isoformat()} for x in items]


def _parse_questions(payload: QuestionImportCreate) -> list[dict[str, Any]]:
    if payload.format == "json":
        try:
            data = json.loads(payload.content)
        except json.JSONDecodeError as exc:
            raise HTTPException(422, f"Invalid JSON: {exc.msg}") from exc
        if isinstance(data, dict):
            data = data.get("questions", [])
        if not isinstance(data, list):
            raise HTTPException(422, "JSON must be an array or {questions: [...]} object")
        return [x for x in data if isinstance(x, dict)]
    reader = csv.DictReader(io.StringIO(payload.content))
    return [dict(row) for row in reader]


@router.post("/api/questions/import/preview")
async def preview_import_questions(payload: QuestionImportCreate, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Dry-run the import: parse, validate and detect duplicates without
    writing anything. The confirm step is the existing POST /api/questions/import."""
    _subject(request)
    rows = _parse_questions(payload)
    if len(rows) > 2500:
        raise HTTPException(422, "A single import is limited to 2500 questions")
    existing_slugs = set((await db.scalars(select(Question.slug))).all())
    preview_rows: list[dict] = []
    to_create = 0
    for index, row in enumerate(rows, 1):
        title = str(row.get("title") or row.get("question") or "").strip()
        answer = str(row.get("answer") or row.get("reference_answer") or "").strip()
        category = str(row.get("category") or "Imported").strip()[:80]
        problems: list[str] = []
        if not title or not answer:
            problems.append("title/answer required")
        slug = str(row.get("slug") or _slugify(f"{category}-{title}"))[:120]
        if slug in existing_slugs:
            problems.append("duplicate slug")
        duplicates = await find_duplicates(db, title) if title and answer else []
        status = "error" if problems else "create"
        if status == "create":
            to_create += 1
        preview_rows.append({
            "row": index,
            "title": title[:255],
            "category": category,
            "status": status,
            "problems": problems,
            "duplicates": duplicates,
        })
    return {
        "total": len(rows),
        "to_create": to_create,
        "to_skip": len(rows) - to_create,
        "rows": preview_rows[:100],
        "truncated": len(preview_rows) > 100,
    }


@router.post("/api/questions/import")
async def import_questions(payload: QuestionImportCreate, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    owner = _subject(request)
    owner_user = (await db.scalars(select(User).where(User.username == owner))).first()
    created_by = owner_user.id if owner_user else None
    rows = _parse_questions(payload)
    if len(rows) > 2500:
        raise HTTPException(422, "A single import is limited to 2500 questions")
    created = 0
    skipped = 0
    errors: list[str] = []
    existing_slugs = set((await db.scalars(select(Question.slug))).all())
    for index, row in enumerate(rows, 1):
        title = str(row.get("title") or row.get("question") or "").strip()
        answer = str(row.get("answer") or row.get("reference_answer") or "").strip()
        category = str(row.get("category") or "Imported").strip()[:80]
        if not title or not answer:
            skipped += 1
            errors.append(f"Row {index}: title/answer required")
            continue
        slug = str(row.get("slug") or _slugify(f"{category}-{title}"))[:120]
        base = slug
        suffix = 2
        while slug in existing_slugs:
            if row.get("slug"):
                break
            slug = f"{base[:112]}-{suffix}"
            suffix += 1
        if slug in existing_slugs:
            skipped += 1
            errors.append(f"Row {index}: duplicate slug {slug}")
            continue
        try:
            difficulty = max(1, min(5, int(row.get("difficulty") or 2)))
        except (TypeError, ValueError):
            difficulty = 2
        db.add(Question(
            slug=slug,
            category=category,
            title=title[:255],
            difficulty=difficulty,
            answer=answer,
            code=str(row.get("code") or ""),
            followups=str(row.get("followups") or ""),
            project_link=str(row.get("project_link") or "")[:120],
            tags="|".join(t.strip() for t in str(row.get("tags") or "").split("|") if t.strip()),
            created_by=created_by,
            updated_at=utc_now(),
        ))
        existing_slugs.add(slug)
        created += 1
    batch = QuestionImportBatch(owner=owner, source_format=payload.format, total=len(rows), created=created, skipped=skipped, errors_json=json.dumps(errors[:100], ensure_ascii=False))
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return {"batch_id": batch.id, "total": len(rows), "created": created, "skipped": skipped, "errors": errors[:100]}


@router.get("/api/questions/import/history")
async def import_history(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict]:
    owner = _subject(request)
    items = (await db.scalars(select(QuestionImportBatch).where(QuestionImportBatch.owner == owner).order_by(QuestionImportBatch.id.desc()).limit(20))).all()
    return [{"id": x.id, "format": x.source_format, "total": x.total, "created": x.created, "skipped": x.skipped, "errors": _safe_json(x.errors_json, []), "created_at": x.created_at.isoformat()} for x in items]


@router.post("/api/repos/{repo_id}/resume")
async def generate_resume(repo_id: int, payload: ResumeGenerateCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    repo = await db.get(Repository, repo_id)
    if not repo or repo.user_id != user.id:
        raise HTTPException(404, "Repository not found")
    files = (await db.scalars(select(RepoFile).where(RepoFile.repository_id == repo_id))).all()
    architecture = build_architecture(files, repo.name)
    topics = [str(name) for name, _ in architecture.get("topics", [])[:8]]
    symbols = architecture.get("symbols", [])
    async_count = sum(1 for s in symbols if s.get("kind") == "async_function")
    class_count = sum(1 for s in symbols if s.get("kind") == "class")
    evidence = {
        "repository": repo.name,
        "provider": repo.provider,
        "files": repo.file_count,
        "topics": topics,
        "python_symbols": len(symbols),
        "async_functions": async_count,
        "classes": class_count,
        "architecture_questions": architecture.get("questions", [])[:5],
    }
    language_name = "Chinese" if payload.language == "zh" else "English"
    prompt = (
        f"Create a truthful {language_name} resume project description from ONLY this repository evidence. "
        "Do not invent business metrics, users, latency, accuracy, team size or deployment scale. "
        f"Style={payload.style}. Return a short project title line and 3 concise impact/engineering bullets. Evidence: {json.dumps(evidence, ensure_ascii=False)}"
    )
    generated = await llm.chat([
        {"role": "system", "content": "You are a technical resume editor. Use only supplied evidence and never fabricate metrics."},
        {"role": "user", "content": prompt},
    ], temperature=0.2, max_tokens=650)
    if generated:
        text = generated.strip()
        provider = "llm"
    elif payload.language == "zh":
        tech = "、".join(topics[:6]) if topics else "Python 工程化"
        text = (
            f"{repo.name}｜代码与架构项目\n"
            f"• 基于真实仓库代码梳理 {repo.file_count} 个文本/代码文件，核心技术覆盖 {tech}。\n"
            f"• 使用 AST 提取函数、类、异步函数和模块依赖，共识别 {len(symbols)} 个 Python 符号，用于生成架构关系和项目面试追问。\n"
            f"• 围绕模块边界、异步 I/O、事务/检索等工程决策生成可验证的项目讲解，描述仅引用仓库静态证据，不虚构业务指标。"
        )
        provider = "offline"
    else:
        tech = ", ".join(topics[:6]) if topics else "Python engineering"
        text = (
            f"{repo.name} | Code & Architecture Project\n"
            f"• Analyzed {repo.file_count} repository files and mapped core technologies including {tech}.\n"
            f"• Used Python AST analysis to extract functions, classes, async functions, and module dependencies across {len(symbols)} symbols for architecture and interview intelligence.\n"
            "• Turned repository evidence into explainable engineering decisions and project interview prompts without inventing product metrics."
        )
        provider = "offline"
    return {"repository": repo.name, "language": payload.language, "style": payload.style, "provider": provider, "evidence": evidence, "text": text}
