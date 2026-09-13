from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: int
    slug: str
    category: str
    title: str
    difficulty: int
    answer: str
    code: str
    followups: str
    project_link: str
    archived: int = 0
    tags: str = ""
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuestionCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1)
    code: str = Field(default="", max_length=20000)
    followups: str = Field(default="", max_length=2000)
    difficulty: int = Field(default=2, ge=1, le=5)
    project_link: str = Field(default="", max_length=120)
    tags: str = Field(default="", max_length=500)


class QuestionUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    answer: str | None = Field(default=None, min_length=1)
    code: str | None = Field(default=None, max_length=20000)
    followups: str | None = Field(default=None, max_length=2000)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    project_link: str | None = Field(default=None, max_length=120)
    tags: str | None = Field(default=None, max_length=500)


class QuestionBulkTag(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    mode: Literal["set", "append", "remove"] = "append"
    tags: list[str] = Field(default_factory=list, max_length=50)


class AnswerCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class AnswerOut(BaseModel):
    id: int
    question_id: int
    content: str
    score: float
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewCreate(BaseModel):
    role: str = "AI / Agent Engineer"
    focus: list[str] = ["Python", "FastAPI", "Agent", "Project", "LeetCode"]
    difficulty: str = "medium"
    duration: int = Field(default=45, ge=15, le=120)
    persona: Literal[
        "normal", "friendly", "pressure", "backend_lead", "agent_lead", "algorithm", "hr"
    ] = "normal"


class InterviewTurnCreate(BaseModel):
    question_id: int | None = None
    module_index: int | None = Field(default=None, ge=0, le=40)
    interviewer_prompt: str = Field(min_length=1, max_length=3000)
    answer: str = Field(min_length=1, max_length=8000)


class CodeRunRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    stdin: str = Field(default="", max_length=4000)


class CodeExplanationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    explanation: str = Field(min_length=1, max_length=8000)
    question_id: int | None = None
    source_title: str = Field(default="Code Lab", max_length=300)


class RepoSyncRequest(BaseModel):
    provider: Literal["github", "gitee"]
    repo: str = Field(min_length=3, max_length=500)
    branch: str = Field(default="master", min_length=1, max_length=120)
    max_files: int = Field(default=260, ge=20, le=500)
    # Provider-side visibility of the source repo (display metadata only).
    is_private: bool = False


class GitCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=8, max_length=128)


class CodingSubmitRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    time_complexity: str = Field(default="", max_length=80)
    space_complexity: str = Field(default="", max_length=80)
    mode: Literal["practice", "lock"] = "practice"


class RegisterCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)


class LoginCreate(BaseModel):
    identity: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class CanvasSave(BaseModel):
    case_id: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=255)
    nodes: list[dict] = Field(default_factory=list, max_length=80)
    edges: list[dict] = Field(default_factory=list, max_length=140)


class TranscriptSave(BaseModel):
    transcript: str = Field(default="", max_length=30000)
    duration_ms: float = Field(default=0, ge=0, le=7_200_000)


class QuestionImportCreate(BaseModel):
    format: Literal["json", "csv"] = "json"
    content: str = Field(min_length=2, max_length=1_500_000)


class ResumeGenerateCreate(BaseModel):
    language: Literal["zh", "en"] = "zh"
    style: Literal["compact", "impact", "technical"] = "technical"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(default="", max_length=200)
    all_devices: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class RepoVisibilityUpdate(BaseModel):
    is_public: bool


class PlaygroundSessionCreate(BaseModel):
    kind: Literal["sql", "redis"]


class PlaygroundSqlRequest(BaseModel):
    session_id: int = Field(ge=1)
    sql: str = Field(min_length=1, max_length=12000)


class PlaygroundRedisRequest(BaseModel):
    session_id: int = Field(ge=1)
    command: str = Field(min_length=1, max_length=1000)


class PlaygroundFastApiRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str = Field(min_length=1, max_length=300, pattern=r"^/[!-~]*$")
    body: str = Field(default="", max_length=6000)


class PlaygroundResetRequest(BaseModel):
    session_id: int = Field(ge=1)


class PortfolioProfileUpdate(BaseModel):
    display_name: str = Field(default="", max_length=120)
    headline: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=4000)
    skills: list[str] = Field(default_factory=list, max_length=30)
    resume_url: str = Field(default="", max_length=500)
    social_links: dict[str, str] = Field(default_factory=dict)
    is_published: bool = False


class PortfolioProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=8000)
    architecture: str = Field(default="", max_length=8000)
    decisions: str = Field(default="", max_length=8000)
    tech_tags: list[str] = Field(default_factory=list, max_length=20)
    link: str = Field(default="", max_length=500)
    repository_id: int | None = Field(default=None, ge=1)
    is_visible: bool = True


class PortfolioProjectUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=8000)
    architecture: str = Field(default="", max_length=8000)
    decisions: str = Field(default="", max_length=8000)
    tech_tags: list[str] = Field(default_factory=list, max_length=20)
    link: str = Field(default="", max_length=500)
    repository_id: int | None = Field(default=None, ge=1)
    is_visible: bool = True


class PortfolioProjectOrder(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=50)
