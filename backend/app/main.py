from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import delete, func, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from .ai import ask_json
from .config import settings
from .db import Base, engine, get_db
from .deps import current_user
from .models import (
    AnswerVersion,
    CodeExplanationAttempt,
    CodingChallenge,
    CodingSubmission,
    CodingWrongEntry,
    GitConnection,
    InterviewReport,
    InterviewSession,
    InterviewTurn,
    Mastery,
    Question,
    RepoFile,
    Repository,
    ReviewLog,
    User,
)
from .repo_sync import analyze_code, clone_and_scan, normalize_repo
from .code_intel import build_architecture
from .git_oauth import decrypt_token
from .git_routes import router as git_router
from .playground_routes import router as playground_router
from .portfolio_routes import router as portfolio_router
from .llm import llm
from .auth import decode_access_token
from .v07 import router as v07_router
from .question_cms import find_duplicates, unique_slug
from .personas import PERSONAS, build_time_plan, get_persona
from .interview_memory import analyze_session, build_memory_context, summarize_findings
from .interview_time import compute_time_status, parse_module_starts, serialize_module_starts
from .schemas import (
    AnswerCreate,
    AnswerOut,
    CodeExplanationCreate,
    CodingSubmitRequest,
    CodeRunRequest,
    InterviewCreate,
    InterviewTurnCreate,
    QuestionBulkTag,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    RepoSyncRequest,
    RepoVisibilityUpdate,
)
from .scoring import score_answer
from .fsrs import (
    ReviewOutcome,
    elapsed_days,
    grade_from_score,
    legacy_state,
    retrievability,
    schedule_review,
)
from .observability import (
    RequestContextMiddleware,
    audit,
    configure_logging,
    init_error_tracking,
    metrics_payload,
)
from .seed import seed
from .timeutil import utc_now

try:
    # Observability must never block startup: an unconfigured or broken
    # setup keeps the app fully functional (offline mode stays intact).
    configure_logging()
    init_error_tracking()
except Exception:  # pragma: no cover - last-resort fallback
    logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic (run `alembic upgrade head` before boot; the
    # Docker entrypoint does this automatically). Startup only seeds content.
    # Module-level names (redis, seed) resolve at call time, so defining the
    # lifespan above them is safe.
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await seed(session)
    yield
    await redis.aclose()


app = FastAPI(title="InterviewOS API", version="1.0.0", lifespan=lifespan)
@app.middleware("http")
async def jwt_guard(request: Request, call_next):
    path = request.url.path
    public = (
        path == "/health"
        or path == "/ready"
        or path == "/metrics"  # process-level counters only, no user data
        or path == "/api/playground/meta"  # static limits/policy info, no user data
        or path.startswith("/api/auth/")
        or path.startswith("/api/portfolio/")
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
        or path.startswith("/redoc")
    )
    if request.method != "OPTIONS" and path.startswith("/api/") and not public:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        try:
            request.state.auth = decode_access_token(header[7:].strip())
        except HTTPException as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Registered last so it runs outermost: request ids and access logs cover
# even the 401s short-circuited by the JWT guard above.
app.add_middleware(RequestContextMiddleware)

app.include_router(v07_router)
app.include_router(git_router)
app.include_router(playground_router)
app.include_router(portfolio_router)
redis = Redis.from_url(settings.redis_url, decode_responses=True)

CATEGORY_TOPIC = {
    "Python": "Python / asyncio",
    "FastAPI": "FastAPI / Depends",
    "Database": "Database / ORM",
    "Backend": "Redis / Cache",
    "Agent": "Agent / Tool Calling",
    "RAG": "RAG",
    "System Design": "System Design",
    "LeetCode": "LeetCode / Algorithms",
}

SYSTEM_DESIGN_CASES = [
    {
        "id": "python-runner",
        "title": "设计一个在线 Python 代码执行平台",
        "requirements": ["在线运行 Python", "限制 CPU/内存/时间/进程", "隔离用户代码", "返回 stdout/stderr", "支持未来多语言扩展"],
        "followups": ["如果用户写 while True 怎么办？", "如果创建大量进程怎么办？", "网络访问应该默认关闭吗？", "如何从单机 Runner 扩展到队列和 worker？"],
        "reference": "Browser -> API -> Queue -> isolated Runner -> Result Store。重点说明沙箱边界、资源限制、超时、网络/文件系统限制、任务状态和横向扩展。",
    },
    {
        "id": "rag-service",
        "title": "设计一个生产级 RAG 问答服务",
        "requirements": ["文档入库", "向量检索", "rerank", "引用证据", "可观测与评测"],
        "followups": ["Chunk 怎么选择？", "召回为空怎么办？", "如何发现 embedding 漂移？", "如何评估检索和生成分别出了问题？"],
        "reference": "Ingestion -> chunk -> embedding/index -> retrieve -> rerank -> prompt -> LLM -> citation，并把检索指标、生成指标、版本化索引和降级策略分开设计。",
    },
    {
        "id": "agent-executor",
        "title": "设计一个可审批、可审计的 Agent 执行系统",
        "requirements": ["自然语言计划", "结构化 Schema", "审批边界", "确定性执行", "审计日志"],
        "followups": ["为什么 Prompt 不能代替权限？", "审批前后哪些字段不能变化？", "如何保证幂等？", "重试会不会造成重复副作用？"],
        "reference": "LLM 只负责提出结构化 Plan，高风险动作必须经过 validation/authorization/approval，再交给确定性 executor，并使用 idempotency key、hash 和 audit log。",
    },
    {
        "id": "interview-platform",
        "title": "设计一个 AI 面试与间隔复习平台",
        "requirements": ["题库", "实时追问", "答案版本", "掌握度", "间隔复习", "项目代码关联"],
        "followups": ["如何避免评分完全依赖 LLM？", "掌握度如何更新？", "如何设计复习队列？", "项目代码变化后怎样刷新问题？"],
        "reference": "Question/AnswerVersion/Mastery/InterviewTurn/Repository 是核心域模型；LLM 负责深挖和反馈，但基础评分、状态和复习调度必须可确定复现。",
    },
]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "time": utc_now().isoformat(), "version": app.version}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness: database and cache connectivity as booleans only — never
    connection errors, hosts or driver details (they stay in server logs)."""
    checks: dict[str, bool] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(sql_text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    try:
        await redis.ping()
        checks["cache"] = True
    except Exception:
        checks["cache"] = False
    ok = all(checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "checks": checks},
        status_code=200 if ok else 503,
    )


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)


async def _invalidate_dashboard(user_id: int) -> None:
    try:
        await redis.delete(f"dashboard:v8:{user_id}")
    except Exception:
        pass


async def _owned_session(db: AsyncSession, session_id: int, user: User) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(404, "Interview session not found")
    return session


async def _owned_repo(db: AsyncSession, repo_id: int, user: User) -> Repository:
    repo = await db.get(Repository, repo_id)
    if not repo or repo.user_id != user.id:
        raise HTTPException(404, "Repository not found")
    return repo


def _review_mastery(item: Mastery, grade: int, *, source: str, score: float, now: datetime) -> tuple[ReviewOutcome, float, int]:
    """Apply one FSRS-4.5 review to a Mastery row.

    Returns (outcome, elapsed_days_before, previous_interval) so the caller
    can log the pre-review state. Rows without FSRS state or review
    timestamps (seeded estimates, legacy fixed-interval rows without the
    0004 backfill) are scheduled as new topics.
    """
    elapsed = elapsed_days(item.last_review_at, now)
    previous_interval = item.interval_days or 0
    outcome = schedule_review(
        grade,
        stability=item.stability,
        difficulty=item.difficulty,
        last_review_at=item.last_review_at,
        now=now,
    )
    item.stability = outcome.stability
    item.difficulty = outcome.difficulty
    item.reps = (item.reps or 0) + 1
    item.lapses = (item.lapses or 0) + (1 if outcome.failed else 0)
    item.last_review_at = now
    item.interval_days = outcome.interval_days
    item.due_at = now + timedelta(days=outcome.interval_days)
    return outcome, elapsed, previous_interval


async def _update_mastery(db: AsyncSession, user_id: int, category: str, score: float, source: str = "answer") -> Mastery:
    topic = CATEGORY_TOPIC.get(category, category)
    now = utc_now()
    item = await db.scalar(select(Mastery).where(Mastery.user_id == user_id, Mastery.topic == topic))
    if not item:
        item = Mastery(user_id=user_id, topic=topic, score=score, due_at=now, interval_days=1)
        db.add(item)
        await db.flush()
    else:
        item.score = round(item.score * 0.7 + score * 0.3, 1)

    grade = grade_from_score(score)
    outcome, elapsed, previous_interval = _review_mastery(item, grade, source=source, score=score, now=now)
    db.add(ReviewLog(
        mastery_id=item.id,
        user_id=user_id,
        topic=item.topic,
        grade=grade,
        source=source,
        score=score,
        stability=outcome.stability,
        difficulty=outcome.difficulty,
        retrievability=outcome.retrievability,
        elapsed_days=round(elapsed, 4) if not outcome.is_new else 0.0,
        scheduled_days=previous_interval,
        reviewed_at=now,
    ))
    return item


async def _activity_streak(db: AsyncSession, user_id: int) -> int:
    """Consecutive days (ending today or yesterday) with at least one
    answer / submission / interview / code-explanation activity."""
    dates: set[str] = set()
    for stmt in (
        select(AnswerVersion.created_at).where(AnswerVersion.user_id == user_id),
        select(CodingSubmission.created_at).where(CodingSubmission.user_id == user_id),
        select(InterviewSession.created_at).where(InterviewSession.user_id == user_id),
        select(CodeExplanationAttempt.created_at).where(CodeExplanationAttempt.user_id == user_id),
    ):
        for value in (await db.scalars(stmt)).all():
            dates.add(value.date().isoformat())
    if not dates:
        return 0
    today = utc_now().date()
    cursor = today if today.isoformat() in dates else today - timedelta(days=1)
    if cursor.isoformat() not in dates:
        return 0
    streak = 0
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@app.get("/api/dashboard")
async def dashboard(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    cache_key = f"dashboard:v8:{user.id}"
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    total = await db.scalar(select(func.count()).select_from(Question)) or 0
    answered = await db.scalar(
        select(func.count(func.distinct(AnswerVersion.question_id))).where(AnswerVersion.user_id == user.id)
    ) or 0
    code_labs = await db.scalar(select(func.count()).select_from(Question).where(Question.code != "")) or 0
    project_count = 3 + (await db.scalar(
        select(func.count()).select_from(Repository).where(Repository.user_id == user.id)
    ) or 0)
    coding_solved = await db.scalar(
        select(func.count(func.distinct(CodingSubmission.challenge_id)))
        .where(CodingSubmission.user_id == user.id, CodingSubmission.passed == 1)
    ) or 0
    coding_wrong = await db.scalar(
        select(func.count()).select_from(CodingWrongEntry)
        .where(CodingWrongEntry.user_id == user.id, CodingWrongEntry.resolved == 0)
    ) or 0
    mastery = (await db.scalars(select(Mastery).where(Mastery.user_id == user.id))).all()
    avg = round(sum(m.score for m in mastery) / len(mastery), 1) if mastery else 0
    due = sum(1 for m in mastery if m.due_at <= utc_now() + timedelta(days=1))
    payload = {
        "readiness": avg,
        "question_total": total,
        "question_answered": answered,
        "code_labs": code_labs,
        "projects": project_count,
        "coding_solved": coding_solved,
        "coding_wrong": coding_wrong,
        "review_due": due,
        "streak": await _activity_streak(db, user.id),
    }
    try:
        await redis.setex(cache_key, 20, json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
    return payload


@app.get("/api/questions", response_model=list[QuestionOut])
async def questions(
    category: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[Question]:
    stmt = select(Question).where(Question.archived == (1 if archived else 0)).order_by(Question.category, Question.id)
    if category:
        stmt = stmt.where(Question.category == category)
    if q:
        stmt = stmt.where(Question.title.ilike(f"%{q}%"))
    return list((await db.scalars(stmt)).all())


@app.get("/api/questions/duplicates")
async def question_duplicates(
    title: str = Query(min_length=1, max_length=255),
    exclude: int | None = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {"duplicates": await find_duplicates(db, title, exclude_id=exclude)}


@app.post("/api/questions", response_model=QuestionOut, status_code=201)
async def create_question(
    payload: QuestionCreate,
    force: bool = False,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    duplicates = await find_duplicates(db, payload.title)
    if not force and any(d["similarity"] >= 0.9 for d in duplicates):
        raise HTTPException(409, {"message": "Possible duplicate question", "duplicates": duplicates})
    question = Question(
        slug=await unique_slug(db, payload.category, payload.title),
        category=payload.category.strip(),
        title=payload.title.strip(),
        difficulty=payload.difficulty,
        answer=payload.answer,
        code=payload.code,
        followups=payload.followups,
        project_link=payload.project_link,
        tags="|".join(t.strip() for t in payload.tags.split("|") if t.strip()) if payload.tags else "",
        created_by=user.id,
        updated_at=utc_now(),
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@app.patch("/api/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    question_id: int,
    payload: QuestionUpdate,
    force: bool = False,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    updates = payload.model_dump(exclude_unset=True)
    next_title = updates.get("title", question.title)
    if next_title != question.title:
        duplicates = await find_duplicates(db, next_title, exclude_id=question.id)
        if not force and any(d["similarity"] >= 0.9 for d in duplicates):
            raise HTTPException(409, {"message": "Possible duplicate question", "duplicates": duplicates})
    for field, value in updates.items():
        setattr(question, field, value.strip() if isinstance(value, str) else value)
    question.updated_at = utc_now()
    await db.commit()
    await db.refresh(question)
    return question


@app.post("/api/questions/{question_id}/archive", response_model=QuestionOut)
async def archive_question(question_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    question.archived = 1
    question.updated_at = utc_now()
    await db.commit()
    await db.refresh(question)
    return question


@app.post("/api/questions/{question_id}/restore", response_model=QuestionOut)
async def restore_question(question_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> Question:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    question.archived = 0
    question.updated_at = utc_now()
    await db.commit()
    await db.refresh(question)
    return question


@app.post("/api/questions/bulk-tag")
async def bulk_tag_questions(payload: QuestionBulkTag, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    wanted = [t.strip() for t in payload.tags if t.strip()]
    items = (await db.scalars(select(Question).where(Question.id.in_(payload.ids)))).all()
    now = utc_now()
    for item in items:
        current = [t for t in item.tags.split("|") if t.strip()]
        if payload.mode == "set":
            merged = list(dict.fromkeys(wanted))
        elif payload.mode == "remove":
            merged = [t for t in current if t not in wanted]
        else:
            merged = list(dict.fromkeys(current + wanted))
        item.tags = "|".join(merged[:30])
        item.updated_at = now
    await db.commit()
    return {"updated": len(items)}


@app.get("/api/questions/{question_id}", response_model=QuestionOut)
async def question_detail(question_id: int, db: AsyncSession = Depends(get_db)) -> Question:
    item = await db.get(Question, question_id)
    if not item:
        raise HTTPException(404, "Question not found")
    return item


@app.post("/api/questions/{question_id}/answers")
async def save_answer(question_id: int, payload: AnswerCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    question = await db.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")

    scored = score_answer(question.answer, payload.content)
    version = AnswerVersion(question_id=question_id, user_id=user.id, content=payload.content, score=scored["score"])
    db.add(version)
    mastery = await _update_mastery(db, user.id, question.category, scored["score"])
    await db.commit()
    await db.refresh(version)
    await _invalidate_dashboard(user.id)
    return {
        "id": version.id,
        "question_id": version.question_id,
        "content": version.content,
        "score": version.score,
        "created_at": version.created_at,
        "dimensions": scored["dimensions"],
        "missing_terms": scored["missing_terms"],
        "mastery": {"topic": mastery.topic, "score": mastery.score, "next_review": mastery.due_at.isoformat()},
    }


@app.get("/api/questions/{question_id}/answers", response_model=list[AnswerOut])
async def answer_versions(question_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[AnswerVersion]:
    stmt = (
        select(AnswerVersion)
        .where(AnswerVersion.question_id == question_id, AnswerVersion.user_id == user.id)
        .order_by(AnswerVersion.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())


@app.get("/api/learning/weakness")
async def weakness(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    items = (await db.scalars(select(Mastery).where(Mastery.user_id == user.id).order_by(Mastery.score, Mastery.due_at))).all()
    now = utc_now()
    result = []
    for x in items:
        stability, difficulty = (x.stability, x.difficulty) if x.stability > 0 and x.difficulty > 0 else legacy_state(x.score, x.interval_days)
        r = retrievability(elapsed_days(x.last_review_at, now), stability)
        result.append({
            "topic": x.topic,
            "score": x.score,
            "due_at": x.due_at.isoformat(),
            "interval_days": x.interval_days,
            "due": x.due_at <= now,
            "stability": round(stability, 2),
            "difficulty": round(difficulty, 2),
            "retrievability": round(r, 4),
            "reps": x.reps,
            "lapses": x.lapses,
            "last_review_at": x.last_review_at.isoformat() if x.last_review_at else None,
        })
    return result


@app.get("/api/learning/{topic:path}/history")
async def review_history(topic: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    item = await db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.topic == topic))
    if not item:
        raise HTTPException(404, "Topic not found")
    logs = (await db.scalars(
        select(ReviewLog)
        .where(ReviewLog.user_id == user.id, ReviewLog.topic == topic)
        .order_by(ReviewLog.reviewed_at.desc(), ReviewLog.id.desc())
        .limit(50)
    )).all()
    return [
        {
            "id": log.id,
            "grade": log.grade,
            "source": log.source,
            "score": log.score,
            "stability": log.stability,
            "difficulty": log.difficulty,
            "retrievability": log.retrievability,
            "elapsed_days": log.elapsed_days,
            "scheduled_days": log.scheduled_days,
            "reviewed_at": log.reviewed_at.isoformat(),
        }
        for log in logs
    ]


@app.post("/api/learning/{topic:path}/review")
async def review_topic(topic: str, grade: int = Query(ge=1, le=5), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    item = await db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.topic == topic))
    if not item:
        raise HTTPException(404, "Topic not found")
    now = utc_now()
    outcome, elapsed, previous_interval = _review_mastery(item, grade, source="manual", score=0.0, now=now)
    db.add(ReviewLog(
        mastery_id=item.id,
        user_id=user.id,
        topic=item.topic,
        grade=grade,
        source="manual",
        score=0.0,
        stability=outcome.stability,
        difficulty=outcome.difficulty,
        retrievability=outcome.retrievability,
        elapsed_days=round(elapsed, 4) if not outcome.is_new else 0.0,
        scheduled_days=previous_interval,
        reviewed_at=now,
    ))
    # Keep the 0-100 display score roughly aligned with manual grades.
    delta = {1: -10, 2: -5, 3: 3, 4: 6, 5: 9}[grade]
    item.score = max(0.0, min(100.0, item.score + delta))
    await db.commit()
    await _invalidate_dashboard(user.id)
    return {
        "topic": item.topic,
        "score": item.score,
        "next_review": item.due_at.isoformat(),
        "interval_days": item.interval_days,
        "stability": item.stability,
        "difficulty": item.difficulty,
        "retrievability": outcome.retrievability,
        "reps": item.reps,
        "lapses": item.lapses,
    }


@app.get("/api/projects")
async def projects() -> list[dict]:
    return [
        {
            "name": "MindTrip",
            "subtitle": "Structured Travel Planning Agent",
            "focus": ["RAG", "LangGraph", "BGE-M3", "Reranker", "Validation"],
            "pipeline": ["Retrieve", "Plan", "Validate", "Repair"],
            "interview_questions": ["为什么 Retrieve 与 Plan 分离？", "证据冲突如何处理？", "Validate 为什么不完全交给 LLM？"],
        },
        {
            "name": "AtlasSplit",
            "subtitle": "Safe Agent Execution Pipeline",
            "focus": ["Structured Plan", "Approval", "Deterministic Executor", "Audit"],
            "pipeline": ["Natural Language", "AllocationPlan", "Validation", "Approval", "Executor", "Audit"],
            "interview_questions": ["为什么不能直接执行 LLM 代码？", "Approval Boundary 放在哪里？", "如何保证幂等和审计？"],
        },
        {
            "name": "InterviewOS",
            "subtitle": "AI Engineer Interview Workbench",
            "focus": ["FastAPI", "Monaco", "Code Runner", "Spaced Review", "AI Interview"],
            "pipeline": ["Learn", "Code", "Interview", "Review"],
            "interview_questions": ["在线代码为什么需要独立 Runner？", "如何设计题库和复习模型？", "如何做项目代码到题库的关联？"],
        },
    ]


def _complexity_key(value: str) -> str:
    return value.lower().replace(" ", "").replace("（", "(").replace("）", ")")


def _challenge_payload(item: CodingChallenge) -> dict:
    return {
        "id": item.id,
        "slug": item.slug,
        "title": item.title,
        "category": item.category,
        "difficulty": item.difficulty,
        "description": item.description,
        "function_name": item.function_name,
        "starter_code": item.starter_code,
        "public_tests": json.loads(item.public_tests or "[]"),
        "hints": item.hints,
        "tags": item.tags.split("|") if item.tags else [],
    }


@app.get("/api/coding/challenges")
async def coding_challenges(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    items = (await db.scalars(select(CodingChallenge).order_by(CodingChallenge.difficulty, CodingChallenge.id))).all()
    solved_ids = set((await db.scalars(
        select(CodingSubmission.challenge_id).where(CodingSubmission.user_id == user.id, CodingSubmission.passed == 1)
    )).all())
    wrong_ids = set((await db.scalars(
        select(CodingWrongEntry.challenge_id).where(CodingWrongEntry.user_id == user.id, CodingWrongEntry.resolved == 0)
    )).all())
    return [{**_challenge_payload(x), "solved": x.id in solved_ids, "wrongbook": x.id in wrong_ids} for x in items]


@app.get("/api/coding/challenges/{challenge_id}")
async def coding_challenge_detail(challenge_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    item = await db.get(CodingChallenge, challenge_id)
    if not item:
        raise HTTPException(404, "Coding challenge not found")
    return _challenge_payload(item)


async def _judge_challenge(challenge: CodingChallenge, code: str, include_hidden: bool) -> dict:
    payload = {
        "code": code,
        "function_name": challenge.function_name,
        "public_tests": json.loads(challenge.public_tests or "[]"),
        "hidden_tests": json.loads(challenge.hidden_tests or "[]"),
        "include_hidden": include_hidden,
    }
    try:
        async with httpx.AsyncClient(timeout=9.0) as client:
            response = await client.post(f"{settings.runner_url}/judge", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Runner unavailable: {exc}") from exc


@app.post("/api/coding/challenges/{challenge_id}/run")
async def run_public_tests(challenge_id: int, payload: CodingSubmitRequest, db: AsyncSession = Depends(get_db)) -> dict:
    challenge = await db.get(CodingChallenge, challenge_id)
    if not challenge:
        raise HTTPException(404, "Coding challenge not found")
    result = await _judge_challenge(challenge, payload.code, include_hidden=False)
    return {
        "public": result["public"],
        "all_public_passed": result["public"]["passed"] == result["public"]["total"],
        "duration_ms": result["duration_ms"],
    }


@app.post("/api/coding/challenges/{challenge_id}/submit")
async def submit_coding_challenge(challenge_id: int, payload: CodingSubmitRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    challenge = await db.get(CodingChallenge, challenge_id)
    if not challenge:
        raise HTTPException(404, "Coding challenge not found")
    result = await _judge_challenge(challenge, payload.code, include_hidden=True)
    public, hidden = result["public"], result["hidden"]
    total = public["total"] + hidden["total"]
    passed_count = public["passed"] + hidden["passed"]
    all_passed = bool(result["all_passed"])
    time_match = bool(payload.time_complexity and _complexity_key(payload.time_complexity) == _complexity_key(challenge.expected_time))
    space_match = bool(payload.space_complexity and _complexity_key(payload.space_complexity) == _complexity_key(challenge.expected_space))
    score = round((passed_count / total * 85 if total else 0) + (7.5 if time_match else 0) + (7.5 if space_match else 0), 1)

    submission = CodingSubmission(
        challenge_id=challenge.id,
        user_id=user.id,
        code=payload.code,
        passed=1 if all_passed else 0,
        public_passed=public["passed"], public_total=public["total"],
        hidden_passed=hidden["passed"], hidden_total=hidden["total"],
        time_complexity=payload.time_complexity, space_complexity=payload.space_complexity,
        time_match=1 if time_match else 0, space_match=1 if space_match else 0,
        mode=payload.mode, duration_ms=result["duration_ms"],
    )
    db.add(submission)

    wrong = await db.scalar(select(CodingWrongEntry).where(CodingWrongEntry.user_id == user.id, CodingWrongEntry.challenge_id == challenge.id))
    failed_public = [f"公开测试 {x.get('index')}：{x.get('error') or '结果不匹配'}" for x in public.get("cases", []) if not x.get("passed")]
    error_text = "；".join(failed_public[:3])
    if hidden["passed"] != hidden["total"]:
        error_text = (error_text + "；" if error_text else "") + f"隐藏测试通过 {hidden['passed']}/{hidden['total']}"
    if all_passed:
        if wrong:
            wrong.resolved = 1
            wrong.last_error = ""
            wrong.last_code = payload.code
            wrong.last_attempt_at = utc_now()
    else:
        if not wrong:
            wrong = CodingWrongEntry(user_id=user.id, challenge_id=challenge.id, attempts=1)
            db.add(wrong)
        else:
            wrong.attempts += 1
        wrong.resolved = 0
        wrong.last_error = error_text or "未通过全部测试"
        wrong.last_code = payload.code
        wrong.last_attempt_at = utc_now()

    mastery = await _update_mastery(db, user.id, "LeetCode", score, source="coding")
    await db.commit()
    await db.refresh(submission)
    await _invalidate_dashboard(user.id)
    return {
        "submission_id": submission.id,
        "all_passed": all_passed,
        "score": score,
        "public": public,
        "hidden": {"passed": hidden["passed"], "total": hidden["total"], "runtime_error": hidden.get("runtime_error", "")},
        "complexity": {
            "time": {"input": payload.time_complexity, "match": time_match, "expected": challenge.expected_time if all_passed else None},
            "space": {"input": payload.space_complexity, "match": space_match, "expected": challenge.expected_space if all_passed else None},
        },
        "reference_solution": challenge.reference_solution if all_passed else None,
        "mastery": {"topic": mastery.topic, "score": mastery.score, "next_review": mastery.due_at.isoformat()},
        "duration_ms": result["duration_ms"],
    }


@app.get("/api/coding/wrongbook")
async def coding_wrongbook(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (await db.execute(
        select(CodingWrongEntry, CodingChallenge)
        .join(CodingChallenge, CodingChallenge.id == CodingWrongEntry.challenge_id)
        .where(CodingWrongEntry.user_id == user.id, CodingWrongEntry.resolved == 0)
        .order_by(CodingWrongEntry.last_attempt_at.desc())
    )).all()
    return [
        {
            "id": wrong.id,
            "challenge_id": challenge.id,
            "title": challenge.title,
            "difficulty": challenge.difficulty,
            "tags": challenge.tags.split("|") if challenge.tags else [],
            "attempts": wrong.attempts,
            "last_error": wrong.last_error,
            "last_code": wrong.last_code,
            "last_attempt_at": wrong.last_attempt_at.isoformat(),
        }
        for wrong, challenge in rows
    ]


@app.get("/api/coding/challenges/{challenge_id}/submissions")
async def coding_submissions(challenge_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    items = (await db.scalars(
        select(CodingSubmission)
        .where(CodingSubmission.challenge_id == challenge_id, CodingSubmission.user_id == user.id)
        .order_by(CodingSubmission.id.desc()).limit(20)
    )).all()
    return [
        {
            "id": x.id, "passed": bool(x.passed), "public": f"{x.public_passed}/{x.public_total}",
            "hidden": f"{x.hidden_passed}/{x.hidden_total}", "score": round((x.public_passed + x.hidden_passed) / max(1, x.public_total + x.hidden_total) * 85 + (7.5 if x.time_match else 0) + (7.5 if x.space_match else 0), 1),
            "mode": x.mode, "duration_ms": x.duration_ms, "created_at": x.created_at.isoformat(),
        }
        for x in items
    ]


@app.post("/api/interviews")
async def create_interview(payload: InterviewCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    focus = payload.focus
    persona = get_persona(payload.persona)
    plan = build_time_plan(payload.duration)
    pool = (await db.scalars(select(Question).where(Question.category.in_(focus), Question.archived == 0))).all()
    if len(pool) < 4:
        pool = (await db.scalars(select(Question).where(Question.archived == 0))).all()
    selected = pool[: plan["max_questions"]]
    script = [
        {"type": "intro", "minutes": plan["intro"], "prompt": persona["intro_prompt"]},
        *[
            {
                "type": q.category,
                "minutes": plan["per_question"],
                "question_id": q.id,
                "prompt": q.title,
                "followups": q.followups.split("|") if q.followups else [],
            }
            for q in selected
        ],
        {"type": "wrap", "minutes": plan["wrap"], "prompt": persona["wrap_prompt"]},
    ]
    session = InterviewSession(
        user_id=user.id,
        role=payload.role,
        focus=",".join(focus),
        difficulty=payload.difficulty,
        duration=payload.duration,
        persona=persona["id"],
        module_starts="{}",
        script=json.dumps(script, ensure_ascii=False),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {
        "id": session.id,
        "role": session.role,
        "difficulty": session.difficulty,
        "duration": session.duration,
        "persona": session.persona,
        "script": script,
    }


@app.get("/api/interviews/personas")
async def interview_personas(user: User = Depends(current_user)) -> list[dict]:
    return [
        {"id": p["id"], "label": p["label"], "description": p["description"], "emphasis": p["emphasis"]}
        for p in PERSONAS.values()
    ]


@app.post("/api/interviews/{session_id}/turn")
async def interview_turn(session_id: int, payload: InterviewTurnCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    session = await _owned_session(db, session_id, user)
    persona = get_persona(session.persona)
    question = await db.get(Question, payload.question_id) if payload.question_id else None
    reference = question.answer if question else payload.interviewer_prompt
    base = score_answer(reference, payload.answer)

    prior = (await db.scalars(
        select(InterviewTurn).where(InterviewTurn.session_id == session_id).order_by(InterviewTurn.id.asc())
    )).all()
    prior_dicts = [
        {"index": i, "prompt": t.interviewer_prompt, "answer": t.user_answer}
        for i, t in enumerate(prior)
    ]
    memory_context = build_memory_context(prior_dicts)

    turn_count_stmt = select(func.count()).select_from(InterviewTurn).where(InterviewTurn.session_id == session_id)
    if payload.question_id:
        turn_count_stmt = turn_count_stmt.where(InterviewTurn.question_id == payload.question_id)
    existing_turns = await db.scalar(turn_count_stmt) or 0
    fallback_followups = question.followups.split("|") if question and question.followups else persona["fallback_followups"]
    fallback_followup = fallback_followups[min(existing_turns, len(fallback_followups) - 1)]

    llm = await ask_json(
        persona["judge_hint"] + f" 评分侧重：{persona['emphasis']} 基于候选人的回答只追问一个最有价值的问题。必须输出 JSON：score(0-100), feedback(一句中文), followup(一个中文追问)。不要输出额外文本。",
        f"岗位：{session.role}\n当前问题：{payload.interviewer_prompt}\n参考要点：{reference}\n候选人回答：{payload.answer}\n基础评分：{base['score']}\n缺失要点：{base['missing_terms']}\n{memory_context}",
    )
    score = float(llm.get("score", base["score"])) if llm else base["score"]
    score = round(max(0, min(100, score)), 1)
    feedback = str(llm.get("feedback", "回答已经覆盖核心概念，可以继续补充失败场景、边界和权衡。")) if llm else (
        "覆盖了主要概念，但还可以补充：" + "、".join(base["missing_terms"][:4]) if base["missing_terms"] else "核心概念覆盖不错，下一步重点讲清失败场景和设计权衡。"
    )
    if not llm and memory_context:
        first_finding = analyze_session(prior_dicts)[0]
        feedback += f" 面试官记忆：{first_finding['detail']}"
    followup = str(llm.get("followup", fallback_followup)) if llm else fallback_followup

    turn = InterviewTurn(
        session_id=session_id,
        user_id=user.id,
        question_id=payload.question_id,
        module_index=payload.module_index,
        interviewer_prompt=payload.interviewer_prompt,
        user_answer=payload.answer,
        score=score,
        feedback=feedback,
        followup=followup,
    )
    db.add(turn)
    if question:
        await _update_mastery(db, user.id, question.category, score)
    await db.commit()
    await _invalidate_dashboard(user.id)
    return {
        "turn_id": turn.id,
        "score": score,
        "dimensions": base["dimensions"],
        "feedback": feedback,
        "followup": followup,
        "missing_terms": base["missing_terms"],
        "mode": "llm" if llm else "offline",
    }


@app.get("/api/interviews/{session_id}/turns")
async def interview_turns(session_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    await _owned_session(db, session_id, user)
    turns = (await db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session_id).order_by(InterviewTurn.id))).all()
    return [
        {
            "id": x.id,
            "prompt": x.interviewer_prompt,
            "answer": x.user_answer,
            "score": x.score,
            "feedback": x.feedback,
            "followup": x.followup,
            "module_index": x.module_index,
        }
        for x in turns
    ]


@app.post("/api/code/run")
async def run_code(payload: CodeRunRequest) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(f"{settings.runner_url}/run", json=payload.model_dump())
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Runner unavailable: {exc}") from exc


@app.post("/api/code/explain")
async def explain_code(payload: CodeExplanationCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    analysis = analyze_code(payload.source_title, payload.code)
    expected = "；".join(analysis["knowledge"] + analysis["symbols"][:6]) or "代码职责、输入输出、控制流、失败边界和复杂度"
    base = score_answer(expected, payload.explanation)
    missing = [x for x in analysis["knowledge"] if x.lower() not in payload.explanation.lower()]
    fallback_feedback = "解释已经抓住主要职责。" if base["score"] >= 75 else "建议按：职责 → 输入输出 → 关键控制流 → 异常/并发边界 → 可优化点 的顺序解释。"
    fallback_followup = analysis["questions"][0] if analysis["questions"] else "如果这段代码在生产环境失败，你会先观察哪三个信号？"

    llm = await ask_json(
        "你是代码面试官。评估候选人对代码的解释，输出 JSON：score(0-100), feedback(两句以内中文), followup(一个追问)。不要输出额外文本。",
        f"来源：{payload.source_title}\n代码：\n{payload.code[:10000]}\n\n候选人解释：{payload.explanation}\n静态分析知识点：{analysis['knowledge']}\n符号：{analysis['symbols']}",
    )
    score = round(float(llm.get("score", base["score"])) if llm else base["score"], 1)
    feedback = str(llm.get("feedback", fallback_feedback)) if llm else fallback_feedback
    followup = str(llm.get("followup", fallback_followup)) if llm else fallback_followup
    attempt = CodeExplanationAttempt(
        question_id=payload.question_id,
        user_id=user.id,
        code=payload.code,
        explanation=payload.explanation,
        score=score,
        feedback=feedback,
        followup=followup,
    )
    db.add(attempt)
    if payload.question_id:
        q = await db.get(Question, payload.question_id)
        if q:
            await _update_mastery(db, user.id, q.category, score, source="explain")
    await db.commit()
    await _invalidate_dashboard(user.id)
    return {
        "score": score,
        "dimensions": base["dimensions"],
        "feedback": feedback,
        "followup": followup,
        "knowledge": analysis["knowledge"],
        "symbols": analysis["symbols"],
        "missing": missing,
        "mode": "llm" if llm else "offline",
    }


@app.post("/api/repos/sync")
async def sync_repo(payload: RepoSyncRequest, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    try:
        normalized_url, _ = normalize_repo(payload.provider, payload.repo)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    repo = await db.scalar(
        select(Repository).where(
            Repository.user_id == user.id,
            Repository.provider == payload.provider,
            Repository.url == normalized_url,
            Repository.branch == payload.branch,
        )
    )
    previous_commit = repo.last_commit if repo else ""
    connection = await db.scalar(
        select(GitConnection).where(GitConnection.user_id == user.id, GitConnection.provider == payload.provider)
    )
    access_token = ""
    if connection and connection.access_token_encrypted:
        try:
            access_token = decrypt_token(connection.access_token_encrypted)
        except ValueError as exc:
            raise HTTPException(
                400,
                "The stored provider token cannot be decrypted (encryption key changed); "
                "disconnect the provider and authorize it again",
            ) from exc
    try:
        scanned = await clone_and_scan(
            payload.provider, payload.repo, payload.branch, payload.max_files,
            previous_commit=previous_commit, access_token=access_token,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc

    if not repo:
        repo = Repository(user_id=user.id, provider=payload.provider, name=scanned["name"], url=scanned["url"], branch=payload.branch)
        db.add(repo)
        await db.flush()
    else:
        await db.execute(delete(RepoFile).where(RepoFile.repository_id == repo.id))

    repo.name = scanned["name"]
    repo.last_commit = scanned["commit"]
    repo.file_count = len(scanned["files"])
    repo.summary = json.dumps(scanned["summary"], ensure_ascii=False)
    repo.is_private = 1 if payload.is_private else 0
    repo.synced_at = utc_now()
    db.add_all([RepoFile(repository_id=repo.id, **item) for item in scanned["files"]])
    await db.commit()
    await db.refresh(repo)
    await _invalidate_dashboard(user.id)
    audit(
        "repo.sync",
        user_id=user.id,
        username=user.username,
        provider=payload.provider,
        repo=scanned["name"],
        branch=payload.branch,
        files=len(scanned["files"]),
    )
    return {
        "id": repo.id,
        "status": "synced",
        "provider": repo.provider,
        "name": repo.name,
        "url": repo.url,
        "branch": repo.branch,
        "last_commit": repo.last_commit,
        "file_count": repo.file_count,
        "summary": json.loads(repo.summary),
        "is_public": bool(repo.is_public),
        "is_private": bool(repo.is_private),
        "synced_at": repo.synced_at.isoformat(),
    }


@app.get("/api/repos")
async def list_repos(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    repos = (await db.scalars(
        select(Repository).where(Repository.user_id == user.id).order_by(Repository.synced_at.desc())
    )).all()
    return [
        {
            "id": x.id,
            "provider": x.provider,
            "name": x.name,
            "url": x.url,
            "branch": x.branch,
            "last_commit": x.last_commit,
            "file_count": x.file_count,
            "summary": json.loads(x.summary or "{}"),
            "is_public": bool(x.is_public),
            "is_private": bool(x.is_private),
            "synced_at": x.synced_at.isoformat(),
        }
        for x in repos
    ]


@app.patch("/api/repos/{repo_id}/visibility")
async def update_repo_visibility(repo_id: int, payload: RepoVisibilityUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    repo = await _owned_repo(db, repo_id, user)
    repo.is_public = 1 if payload.is_public else 0
    await db.commit()
    return {"id": repo.id, "name": repo.name, "is_public": bool(repo.is_public)}


@app.get("/api/repos/{repo_id}/files")
async def list_repo_files(repo_id: int, q: str | None = Query(default=None, max_length=120), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    await _owned_repo(db, repo_id, user)
    stmt = select(RepoFile).where(RepoFile.repository_id == repo_id).order_by(RepoFile.path)
    if q:
        stmt = stmt.where(RepoFile.path.ilike(f"%{q}%"))
    files = (await db.scalars(stmt)).all()
    return [
        {
            "id": x.id,
            "path": x.path,
            "language": x.language,
            "size": x.size,
            "knowledge": json.loads(x.knowledge or "[]"),
            "symbols": json.loads(x.symbols or "[]"),
        }
        for x in files
    ]


@app.get("/api/repos/{repo_id}/files/{file_id}")
async def repo_file_detail(repo_id: int, file_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    await _owned_repo(db, repo_id, user)
    item = await db.get(RepoFile, file_id)
    if not item or item.repository_id != repo_id:
        raise HTTPException(404, "Repository file not found")
    return {
        "id": item.id,
        "path": item.path,
        "language": item.language,
        "size": item.size,
        "content": item.content,
        "knowledge": json.loads(item.knowledge or "[]"),
        "symbols": json.loads(item.symbols or "[]"),
        "questions": json.loads(item.questions or "[]"),
    }


@app.get("/api/system-design/cases")
async def system_design_cases() -> list[dict]:
    return SYSTEM_DESIGN_CASES


@app.post("/api/system-design/{case_id}/evaluate")
async def evaluate_system_design(case_id: str, answer: AnswerCreate) -> dict:
    case = next((x for x in SYSTEM_DESIGN_CASES if x["id"] == case_id), None)
    if not case:
        raise HTTPException(404, "System design case not found")
    base = score_answer(case["reference"], answer.content)
    return {
        **base,
        "feedback": "先覆盖需求和核心组件，再主动讲容量、失败、数据一致性、安全边界和可观测性。",
        "next_followup": case["followups"][0],
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/llm/status")
async def llm_status() -> dict:
    return {
        "enabled": llm.enabled,
        "mode": "openai-compatible" if llm.enabled else "offline",
        "model": llm.model if llm.enabled else "deterministic-fallback",
        "base_url": llm.base_url if llm.enabled else "",
    }


@app.post("/api/interviews/{session_id}/stream-turn")
async def stream_interview_turn(session_id: int, payload: InterviewTurnCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    session = await _owned_session(db, session_id, user)
    persona = get_persona(session.persona)
    question = await db.get(Question, payload.question_id) if payload.question_id else None
    reference = question.answer if question else payload.interviewer_prompt
    base = score_answer(reference, payload.answer)

    prior = (await db.scalars(
        select(InterviewTurn).where(InterviewTurn.session_id == session_id).order_by(InterviewTurn.id.asc())
    )).all()
    history = "\n".join(
        f"Q: {turn.interviewer_prompt}\nA: {turn.user_answer}\nScore: {turn.score}"
        for turn in prior
    )
    prior_dicts = [
        {"index": i, "prompt": t.interviewer_prompt, "answer": t.user_answer}
        for i, t in enumerate(prior)
    ]
    memory_context = build_memory_context(prior_dicts)
    fallback_followups = question.followups.split("|") if question and question.followups else persona["fallback_followups"]
    fallback = fallback_followups[min(len(prior), len(fallback_followups) - 1)]

    judge = await llm.chat_json(
        persona["judge_hint"] + f" 评分侧重：{persona['emphasis']} 输出 JSON，字段必须是 score(0-100), feedback(不超过70字), weakness(不超过30字), followup(只问一个最有价值的中文问题)。不要输出其他内容。",
        f"岗位：{session.role}\n问题：{payload.interviewer_prompt}\n参考要点：{reference}\n候选人回答：{payload.answer}\n基础评分：{base['score']}\n缺失：{base['missing_terms']}\n历史：\n{history}\n{memory_context}",
    )
    score = round(max(0, min(100, float(judge.get("score", base["score"])))) if judge else base["score"], 1)
    feedback = str(judge.get("feedback", "核心概念已经覆盖。继续补充失败场景、边界条件和验证方式。")) if judge else (
        "建议补充：" + "、".join(base["missing_terms"][:4]) if base["missing_terms"] else "核心概念覆盖不错，继续讲清失败边界和工程权衡。"
    )
    if not judge and memory_context:
        first_finding = analyze_session(prior_dicts)[0]
        feedback += f" 面试官记忆：{first_finding['detail']}"
    weakness = str(judge.get("weakness", base["missing_terms"][0] if base["missing_terms"] else "工程边界")) if judge else (base["missing_terms"][0] if base["missing_terms"] else "工程边界")
    target_followup = str(judge.get("followup", fallback)) if judge else fallback

    turn = InterviewTurn(
        session_id=session_id,
        user_id=user.id,
        question_id=payload.question_id,
        module_index=payload.module_index,
        interviewer_prompt=payload.interviewer_prompt,
        user_answer=payload.answer,
        score=score,
        feedback=feedback,
        followup=target_followup,
    )
    db.add(turn)
    if question:
        await _update_mastery(db, user.id, question.category, score, source="interview")
    await db.commit()
    await db.refresh(turn)
    await _invalidate_dashboard(user.id)

    async def events():
        yield _sse("analysis", {"score": score, "feedback": feedback, "weakness": weakness, "mode": "llm" if llm.enabled else "offline"})
        yield _sse("followup_start", {"turn_id": turn.id})
        messages = [
            {"role": "system", "content": f"你是 AI 工程师面试官，{persona['followup_style']} 只输出一个简洁、具体、能继续深挖候选人回答的中文追问，不要给答案。"},
            {"role": "user", "content": f"当前问题：{payload.interviewer_prompt}\n候选人回答：{payload.answer}\n请围绕其最薄弱处追问。建议追问：{target_followup}\n{memory_context}"},
        ]
        streamed = ""
        async for token in llm.stream(messages, fallback_text=target_followup):
            streamed += token
            yield _sse("token", {"content": token})
        final_followup = streamed.strip() or target_followup
        if final_followup != turn.followup:
            turn.followup = final_followup
            await db.commit()
        yield _sse("done", {"turn_id": turn.id, "followup": final_followup})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/repos/{repo_id}/architecture")
async def repository_architecture(repo_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    repo = await _owned_repo(db, repo_id, user)
    files = (await db.scalars(select(RepoFile).where(RepoFile.repository_id == repo_id))).all()
    return build_architecture(files, repo.name)


def _category_for_turn(turn: InterviewTurn, question: Question | None) -> str:
    if question:
        return question.category
    prompt = turn.interviewer_prompt.lower()
    for key in ["python", "fastapi", "agent", "rag", "redis", "database", "system design", "leetcode"]:
        if key in prompt:
            return key.title()
    return "Project"


async def _build_report(session_id: int, db: AsyncSession) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Interview session not found")
    turns = (await db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session_id).order_by(InterviewTurn.id))).all()
    if not turns:
        return {
            "session_id": session_id,
            "role": session.role,
            "created_at": session.created_at.isoformat(),
            "persona": session.persona,
            "turns": 0,
            "overall_score": 0,
            "skill_scores": {},
            "strengths": [],
            "weaknesses": [],
            "review_plan": [],
            "summary": "还没有完成面试回答。",
            "memory": {"findings": [], "summary": "还没有完成面试回答。"},
            "time": compute_time_status(json.loads(session.script or "[]"), parse_module_starts(session.module_starts), utc_now(), session.duration),
        }

    question_ids = [x.question_id for x in turns if x.question_id]
    questions = (await db.scalars(select(Question).where(Question.id.in_(question_ids)))).all() if question_ids else []
    qmap = {q.id: q for q in questions}
    grouped: dict[str, list[float]] = {}
    for turn in turns:
        category = _category_for_turn(turn, qmap.get(turn.question_id))
        grouped.setdefault(category, []).append(turn.score)
    skill_scores = {k: round(sum(v) / len(v), 1) for k, v in grouped.items()}
    overall = round(sum(x.score for x in turns) / len(turns), 1)
    ordered = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)
    strengths = [name for name, score in ordered if score >= 78][:3]
    weaknesses = [name for name, score in reversed(ordered) if score < 78][:4]
    if not weaknesses and ordered:
        weaknesses = [ordered[-1][0]]
    review_plan = []
    for i, name in enumerate(weaknesses[:4], 1):
        review_plan.append({"day": i, "topic": name, "task": f"复习 {name} 核心题 + 1 次项目追问 + 1 个代码/系统设计实验"})
    summary = f"本次 {session.role} 模拟面试共完成 {len(turns)} 个回答，综合得分 {overall}。重点保持 {', '.join(strengths) if strengths else '基础表达'}，下一轮优先补强 {', '.join(weaknesses)}。"

    turn_dicts = [
        {
            "index": i,
            "prompt": turn.interviewer_prompt,
            "answer": turn.user_answer,
            "reference": qmap[turn.question_id].answer if turn.question_id and turn.question_id in qmap else turn.interviewer_prompt,
        }
        for i, turn in enumerate(turns)
    ]
    findings = analyze_session(turn_dicts)
    memory = {"findings": findings, "summary": await summarize_findings(findings)}
    time_execution = compute_time_status(
        json.loads(session.script or "[]"), parse_module_starts(session.module_starts), utc_now(), session.duration
    )

    existing = await db.scalar(select(InterviewReport).where(InterviewReport.session_id == session_id).order_by(InterviewReport.id.desc()))
    if not existing:
        existing = InterviewReport(session_id=session_id, user_id=session.user_id)
        db.add(existing)
    if existing.user_id is None and session.user_id is not None:
        existing.user_id = session.user_id
    existing.overall_score = overall
    existing.skill_scores = json.dumps(skill_scores, ensure_ascii=False)
    existing.strengths = json.dumps(strengths, ensure_ascii=False)
    existing.weaknesses = json.dumps(weaknesses, ensure_ascii=False)
    existing.review_plan = json.dumps(review_plan, ensure_ascii=False)
    existing.summary = summary
    existing.memory_findings = json.dumps(memory, ensure_ascii=False)
    existing.time_execution = json.dumps(time_execution, ensure_ascii=False)
    await db.commit()
    return {
        "session_id": session_id,
        "role": session.role,
        "created_at": session.created_at.isoformat(),
        "persona": session.persona,
        "turns": len(turns),
        "overall_score": overall,
        "skill_scores": skill_scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "review_plan": review_plan,
        "summary": summary,
        "memory": memory,
        "time": time_execution,
    }


@app.get("/api/interviews/{session_id}/report")
async def interview_report(session_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    await _owned_session(db, session_id, user)
    return await _build_report(session_id, db)


def _time_status_payload(session: InterviewSession) -> dict:
    status = compute_time_status(
        json.loads(session.script or "[]"),
        parse_module_starts(session.module_starts),
        utc_now(),
        session.duration,
    )
    status["session_id"] = session.id
    status["persona"] = session.persona
    return status


@app.post("/api/interviews/{session_id}/modules/{module_index}/start")
async def start_interview_module(session_id: int, module_index: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    session = await _owned_session(db, session_id, user)
    script = json.loads(session.script or "[]")
    if not 0 <= module_index < len(script):
        raise HTTPException(404, "Module not found")
    starts = parse_module_starts(session.module_starts)
    if module_index not in starts:
        starts[module_index] = utc_now()
        session.module_starts = serialize_module_starts(starts)
        await db.commit()
        await db.refresh(session)
    return _time_status_payload(session)


@app.get("/api/interviews/{session_id}/time-status")
async def interview_time_status(session_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    session = await _owned_session(db, session_id, user)
    return _time_status_payload(session)


@app.get("/api/reports/latest")
async def latest_report(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    session = await db.scalar(
        select(InterviewSession).where(InterviewSession.user_id == user.id).order_by(InterviewSession.id.desc())
    )
    if not session:
        return {
            "session_id": None,
            "overall_score": 0,
            "skill_scores": {},
            "strengths": [],
            "weaknesses": [],
            "review_plan": [],
            "summary": "还没有面试记录。",
            "memory": {"findings": [], "summary": ""},
            "time": {"plan_minutes": 0, "elapsed_minutes": 0, "current_module": None, "modules": [], "advisory": ""},
        }
    return await _build_report(session.id, db)


@app.get("/api/reports/history")
async def report_history(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[dict]:
    sessions = (await db.scalars(
        select(InterviewSession).where(InterviewSession.user_id == user.id).order_by(InterviewSession.id.desc()).limit(20)
    )).all()
    result = []
    for session in sessions:
        turns = (await db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == session.id))).all()
        if not turns:
            continue
        result.append({
            "session_id": session.id,
            "role": session.role,
            "created_at": session.created_at.isoformat(),
            "overall_score": round(sum(t.score for t in turns) / len(turns), 1),
            "turns": len(turns),
        })
    return result
