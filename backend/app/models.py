from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utc_now


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255))
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    answer: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text, default="")
    followups: Mapped[str] = mapped_column(Text, default="")
    project_link: Mapped[str] = mapped_column(String(120), default="")
    archived: Mapped[int] = mapped_column(Integer, default=0, index=True)
    tags: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnswerVersion(Base):
    __tablename__ = "answer_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    question: Mapped[Question] = relationship()


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("user_id", "topic", name="uq_mastery_user_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(120), index=True)
    score: Mapped[float] = mapped_column(Float, default=50)
    due_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    # FSRS-4.5 memory state; stability/difficulty of 0 marks a legacy row
    # from the fixed-interval scheduler that has not been FSRS-seeded yet.
    stability: Mapped[float] = mapped_column(Float, default=0)
    difficulty: Mapped[float] = mapped_column(Float, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mastery_id: Mapped[int] = mapped_column(ForeignKey("mastery.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(120), index=True)
    grade: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    score: Mapped[float] = mapped_column(Float, default=0)
    stability: Mapped[float] = mapped_column(Float, default=0)
    difficulty: Mapped[float] = mapped_column(Float, default=0)
    retrievability: Mapped[float] = mapped_column(Float, default=0)
    elapsed_days: Mapped[float] = mapped_column(Float, default=0)
    scheduled_days: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(120))
    focus: Mapped[str] = mapped_column(String(255))
    difficulty: Mapped[str] = mapped_column(String(40), default="medium")
    duration: Mapped[int] = mapped_column(Integer, default=45)
    # v0.9: interviewer persona id (personas.PERSONAS key); only styles the
    # questioning and scoring emphasis, never the factual standard.
    persona: Mapped[str] = mapped_column(String(40), default="normal", server_default="normal")
    # v0.9: JSON {module_index: iso_timestamp} recording when each script
    # module was activated, so elapsed time covers thinking time too.
    module_starts: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    script: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"), nullable=True)
    # v0.9: index into InterviewSession.script this turn belongs to, used by
    # the time controller to attribute answers to module budgets.
    module_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interviewer_prompt: Mapped[str] = mapped_column(Text)
    user_answer: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    feedback: Mapped[str] = mapped_column(Text, default="")
    followup: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CodeExplanationAttempt(Base):
    __tablename__ = "code_explanation_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0)
    feedback: Mapped[str] = mapped_column(Text, default="")
    followup: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "provider", "url", "branch", name="uq_repository_user_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(500))
    branch: Mapped[str] = mapped_column(String(120), default="master")
    last_commit: Mapped[str] = mapped_column(String(64), default="")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="{}")
    is_public: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # v1.0: provider-side visibility of the source repository (display
    # metadata only; portfolio exposure is still governed by is_public).
    is_private: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GitConnection(Base):
    """A user's authorized GitHub/Gitee account. The provider access token is
    stored encrypted (app/git_oauth.py) and never returned by any API or
    written to logs; deleting the row revokes the local grant."""

    __tablename__ = "git_connections"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_git_connection_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    provider_login: Mapped[str] = mapped_column(String(160), default="", server_default="")
    provider_user_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    access_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(String(255), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class OAuthState(Base):
    """Single-use CSRF state binding one authorization request to the user
    who started it. Consumed on callback and expired after 10 minutes."""

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RepoFile(Base):
    __tablename__ = "repo_files"
    __table_args__ = (UniqueConstraint("repository_id", "path", name="uq_repo_file_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(700), index=True)
    language: Mapped[str] = mapped_column(String(80), default="Text")
    size: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    symbols: Mapped[str] = mapped_column(Text, default="[]")
    knowledge: Mapped[str] = mapped_column(Text, default="[]")
    questions: Mapped[str] = mapped_column(Text, default="[]")


class CodingChallenge(Base):
    __tablename__ = "coding_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), default="LeetCode", index=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    description: Mapped[str] = mapped_column(Text)
    function_name: Mapped[str] = mapped_column(String(120))
    starter_code: Mapped[str] = mapped_column(Text)
    reference_solution: Mapped[str] = mapped_column(Text, default="")
    public_tests: Mapped[str] = mapped_column(Text, default="[]")
    hidden_tests: Mapped[str] = mapped_column(Text, default="[]")
    expected_time: Mapped[str] = mapped_column(String(80), default="")
    expected_space: Mapped[str] = mapped_column(String(80), default="")
    hints: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")


class CodingSubmission(Base):
    __tablename__ = "coding_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("coding_challenges.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(Text)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    public_passed: Mapped[int] = mapped_column(Integer, default=0)
    public_total: Mapped[int] = mapped_column(Integer, default=0)
    hidden_passed: Mapped[int] = mapped_column(Integer, default=0)
    hidden_total: Mapped[int] = mapped_column(Integer, default=0)
    time_complexity: Mapped[str] = mapped_column(String(80), default="")
    space_complexity: Mapped[str] = mapped_column(String(80), default="")
    time_match: Mapped[int] = mapped_column(Integer, default=0)
    space_match: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(30), default="practice")
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CodingWrongEntry(Base):
    __tablename__ = "coding_wrongbook"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id", name="uq_coding_wrong_user_challenge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("coding_challenges.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_code: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class InterviewReport(Base):
    __tablename__ = "interview_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0)
    skill_scores: Mapped[str] = mapped_column(Text, default="{}")
    strengths: Mapped[str] = mapped_column(Text, default="[]")
    weaknesses: Mapped[str] = mapped_column(Text, default="[]")
    review_plan: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str] = mapped_column(Text, default="")
    # v0.9: JSON {"findings": [...], "summary": "..."} — deterministic
    # interview-memory findings (contradictions / unanswered / evasions /
    # avoided concepts / reused gaps) plus an LLM-augmented summary.
    memory_findings: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    # v0.9: JSON {"plan_minutes", "elapsed_minutes", "modules": [...],
    # "advisory"} — planned vs actual time per script module.
    time_execution: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    tokens_valid_after: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime(1970, 1, 1), server_default="1970-01-01 00:00:00"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SystemDesignCanvas(Base):
    __tablename__ = "system_design_canvases"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(80), index=True)
    case_id: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    nodes_json: Mapped[str] = mapped_column(Text, default="[]")
    edges_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class InterviewRecording(Base):
    __tablename__ = "interview_recordings"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    owner: Mapped[str] = mapped_column(String(80), index=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="audio/webm")
    file_path: Mapped[str] = mapped_column(String(700))
    transcript: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class QuestionImportBatch(Base):
    __tablename__ = "question_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(80), index=True)
    source_format: Mapped[str] = mapped_column(String(20), default="json")
    total: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class KnowledgeNode(Base):
    """Shared knowledge point in a prerequisite chain. `chain` matches the
    Mastery topic it maps to (e.g. "Python / asyncio"), so per-user progress
    stays at the existing mastery granularity while the graph itself is
    identical for everyone."""

    __tablename__ = "knowledge_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    chain: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class PrerequisiteEdge(Base):
    """Directed edge: from_slug must be learned before to_slug. Shared seed
    data; no user ownership."""

    __tablename__ = "prerequisite_edges"
    __table_args__ = (UniqueConstraint("from_slug", "to_slug", name="uq_prerequisite_edge"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_slug: Mapped[str] = mapped_column(String(120), index=True)
    to_slug: Mapped[str] = mapped_column(String(120), index=True)


class PlaygroundSession(Base):
    """A user's sandbox session for one playground kind (sql / redis). The
    session key is an unguessable uuid4 hex sent to the runner, which derives
    the isolated PostgreSQL schema name and Redis database index from it. Rows
    expire after PLAYGROUND_SESSION_TTL_HOURS; expired rows are lazily deleted
    when new sessions are created. No user data is stored here — the sandbox
    contents live only inside the runner's sandbox services."""

    __tablename__ = "playground_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class PortfolioProfile(Base):
    """A user's configurable public portfolio (v1.0 P2 CMS). One row per user;
    `is_published` is the master visibility switch — while off, the public
    portfolio endpoint keeps serving the legacy static view, and once on it
    serves exactly the fields configured here. Never stores private learning
    data."""

    __tablename__ = "portfolio_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    headline: Mapped[str] = mapped_column(String(200), default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    skills_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    is_published: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    resume_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    social_links_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class PortfolioProject(Base):
    """A user-authored portfolio project entry (v1.0 P2 CMS). Optionally bound
    to one of the user's synced repositories for live code evidence; the public
    view only reveals the bound repository's name/url when the repository
    itself is marked public. `is_visible` hides individual entries without
    touching the rest of the portfolio; `order_index` is the user's ordering."""

    __tablename__ = "portfolio_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[int | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    subtitle: Mapped[str] = mapped_column(String(255), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    architecture: Mapped[str] = mapped_column(Text, default="", server_default="")
    decisions: Mapped[str] = mapped_column(Text, default="", server_default="")
    tech_tags_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    link: Mapped[str] = mapped_column(String(500), default="", server_default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_visible: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
