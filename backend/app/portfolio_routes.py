"""v1.0 P2 Portfolio CMS: user-configurable public portfolio.

Two route groups live here:

- `/api/portfolio-cms/*` — the authenticated editor API (profile fields,
  project entries, ordering, publishing). All user-scoped; foreign ids are
  indistinguishable from missing ones (404).
- `/api/portfolio/{username}` — the anonymous public view. While the owner's
  profile is unpublished it keeps serving the legacy static shape (exact field
  set, covered by test_privacy_portfolio.py); once published it serves the CMS
  profile plus the user's visible project entries. Private learning data
  (wrong book, mastery, answers, recordings) never appears in either view.

Bound repositories: a portfolio project may link one of the user's synced
repositories, but the public view only reveals the repository's name/url when
the repository itself is marked public — provider-side `is_private` and the
portfolio toggle `is_public` stay decoupled, exactly like the repositories
section.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .deps import current_user
from .models import InterviewSession, InterviewTurn, PortfolioProfile, PortfolioProject, Repository, User
from .schemas import (
    PortfolioProfileUpdate,
    PortfolioProjectCreate,
    PortfolioProjectOrder,
    PortfolioProjectUpdate,
)

router = APIRouter()

MAX_PROJECTS_PER_USER = 30


def _load_json_array(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _load_json_dict(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items() if str(value).strip()}


def _profile_payload(profile: PortfolioProfile, user: User) -> dict[str, Any]:
    return {
        "display_name": profile.display_name or user.display_name or user.username,
        "headline": profile.headline,
        "summary": profile.summary,
        "skills": _load_json_array(profile.skills_json),
        "resume_url": profile.resume_url,
        "social_links": _load_json_dict(profile.social_links_json),
        "is_published": bool(profile.is_published),
    }


def _project_payload(project: PortfolioProject, repository: Repository | None) -> dict[str, Any]:
    # The caller decides what to pass: the editor passes any of the user's
    # repositories, the public view passes only public ones — so a private
    # repository bound to a visible project never leaks its URL.
    repository_view = None
    if repository is not None:
        repository_view = {
            "name": repository.name,
            "provider": repository.provider,
            "url": repository.url,
            "commit": (repository.last_commit or "")[:12],
            "files": repository.file_count,
        }
    return {
        "id": project.id,
        "title": project.title,
        "subtitle": project.subtitle,
        "description": project.description,
        "architecture": project.architecture,
        "decisions": project.decisions,
        "tech_tags": _load_json_array(project.tech_tags_json),
        "link": project.link,
        "repository_id": project.repository_id,
        "repository": repository_view,
        "is_visible": bool(project.is_visible),
        "order_index": project.order_index,
    }


async def _get_or_create_profile(db: AsyncSession, user: User) -> PortfolioProfile:
    profile = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.user_id == user.id))
    if not profile:
        profile = PortfolioProfile(user_id=user.id)
        db.add(profile)
        await db.commit()
    return profile


async def _owned_project(db: AsyncSession, user: User, project_id: int) -> PortfolioProject:
    project = await db.scalar(
        select(PortfolioProject).where(PortfolioProject.id == project_id, PortfolioProject.user_id == user.id)
    )
    if not project:
        # 404 for missing and foreign ids alike: other users' project ids are
        # indistinguishable from non-existent ones.
        raise HTTPException(404, "Portfolio project not found")
    return project


async def _owned_repository(db: AsyncSession, user: User, repository_id: int | None) -> int | None:
    """Validate that repository_id (if given) is one of the user's synced
    repositories; a foreign or missing id is rejected rather than silently
    bound to someone else's code evidence."""
    if repository_id is None:
        return None
    repository = await db.scalar(
        select(Repository).where(Repository.id == repository_id, Repository.user_id == user.id)
    )
    if not repository:
        raise HTTPException(404, "Repository not found among your synced repositories")
    return repository.id


# --------------------------------------------------------------------------
# CMS: profile
# --------------------------------------------------------------------------


@router.get("/api/portfolio-cms/profile")
async def get_portfolio_profile(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    profile = await _get_or_create_profile(db, user)
    return {"username": user.username, **_profile_payload(profile, user)}


@router.put("/api/portfolio-cms/profile")
async def update_portfolio_profile(
    payload: PortfolioProfileUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    profile = await _get_or_create_profile(db, user)
    profile.display_name = payload.display_name.strip()[:120]
    profile.headline = payload.headline.strip()[:200]
    profile.summary = payload.summary.strip()[:4000]
    profile.skills_json = json.dumps(
        [skill.strip()[:60] for skill in payload.skills if skill.strip()][:30], ensure_ascii=False
    )
    profile.resume_url = payload.resume_url.strip()[:500]
    profile.social_links_json = json.dumps(
        {key.strip()[:40]: value.strip()[:500] for key, value in payload.social_links.items() if value.strip()},
        ensure_ascii=False,
    )
    profile.is_published = 1 if payload.is_published else 0
    await db.commit()
    return {"username": user.username, **_profile_payload(profile, user)}


# --------------------------------------------------------------------------
# CMS: projects
# --------------------------------------------------------------------------


@router.get("/api/portfolio-cms/projects")
async def list_portfolio_projects(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    projects = (await db.scalars(
        select(PortfolioProject)
        .where(PortfolioProject.user_id == user.id)
        .order_by(PortfolioProject.order_index, PortfolioProject.id)
    )).all()
    repos = {r.id: r for r in (await db.scalars(select(Repository).where(Repository.user_id == user.id))).all()}
    return [
        _project_payload(project, repos.get(project.repository_id) if project.repository_id else None)
        for project in projects
    ]


@router.post("/api/portfolio-cms/projects")
async def create_portfolio_project(
    payload: PortfolioProjectCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    count = len(
        (await db.scalars(select(PortfolioProject.id).where(PortfolioProject.user_id == user.id))).all()
    )
    if count >= MAX_PROJECTS_PER_USER:
        raise HTTPException(400, f"Portfolio is limited to {MAX_PROJECTS_PER_USER} projects")
    repository_id = await _owned_repository(db, user, payload.repository_id)
    max_order = await db.scalar(
        select(PortfolioProject.order_index)
        .where(PortfolioProject.user_id == user.id)
        .order_by(PortfolioProject.order_index.desc())
        .limit(1)
    )
    project = PortfolioProject(
        user_id=user.id,
        repository_id=repository_id,
        title=payload.title.strip()[:160],
        subtitle=payload.subtitle.strip()[:255],
        description=payload.description.strip(),
        architecture=payload.architecture.strip(),
        decisions=payload.decisions.strip(),
        tech_tags_json=json.dumps(
            [tag.strip()[:40] for tag in payload.tech_tags if tag.strip()][:20], ensure_ascii=False
        ),
        link=payload.link.strip()[:500],
        order_index=(max_order or 0) + 1,
        is_visible=1 if payload.is_visible else 0,
    )
    db.add(project)
    await db.commit()
    repository = None
    if repository_id:
        repository = await db.scalar(select(Repository).where(Repository.id == repository_id))
    return _project_payload(project, repository)


@router.put("/api/portfolio-cms/projects/order")
async def reorder_portfolio_projects(
    payload: PortfolioProjectOrder,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    projects = (await db.scalars(
        select(PortfolioProject).where(PortfolioProject.user_id == user.id)
    )).all()
    by_id = {project.id: project for project in projects}
    if sorted(payload.ids) != sorted(by_id):
        raise HTTPException(400, "Order payload must cover exactly your portfolio projects")
    for position, project_id in enumerate(payload.ids, start=1):
        by_id[project_id].order_index = position
    await db.commit()
    return await list_portfolio_projects(user=user, db=db)


@router.put("/api/portfolio-cms/projects/{project_id}")
async def update_portfolio_project(
    project_id: int,
    payload: PortfolioProjectUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await _owned_project(db, user, project_id)
    project.repository_id = await _owned_repository(db, user, payload.repository_id)
    project.title = payload.title.strip()[:160]
    project.subtitle = payload.subtitle.strip()[:255]
    project.description = payload.description.strip()
    project.architecture = payload.architecture.strip()
    project.decisions = payload.decisions.strip()
    project.tech_tags_json = json.dumps(
        [tag.strip()[:40] for tag in payload.tech_tags if tag.strip()][:20], ensure_ascii=False
    )
    project.link = payload.link.strip()[:500]
    project.is_visible = 1 if payload.is_visible else 0
    await db.commit()
    repository = None
    if project.repository_id:
        repository = await db.scalar(select(Repository).where(Repository.id == project.repository_id))
    return _project_payload(project, repository)


@router.delete("/api/portfolio-cms/projects/{project_id}")
async def delete_portfolio_project(
    project_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    project = await _owned_project(db, user, project_id)
    await db.delete(project)
    await db.commit()
    return {"deleted": project_id}


# --------------------------------------------------------------------------
# Public portfolio view
# --------------------------------------------------------------------------


async def _latest_interview_score(db: AsyncSession, owner: User) -> float | None:
    latest = await db.scalar(
        select(InterviewSession).where(InterviewSession.user_id == owner.id).order_by(InterviewSession.id.desc())
    )
    if not latest:
        return None
    turns = (await db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == latest.id))).all()
    if not turns:
        return None
    return round(sum(turn.score for turn in turns) / len(turns), 1)


_LEGACY_PROJECTS = [
    {"name": "MindTrip", "subtitle": "Structured travel-planning Agent", "pipeline": ["Retrieve", "Plan", "Validate", "Repair"], "decision": "把生成与确定性验证分开，减少不可执行计划。"},
    {"name": "AtlasSplit", "subtitle": "Safe deterministic execution Agent", "pipeline": ["Plan", "Validate", "Approval", "Executor", "Audit"], "decision": "LLM 提计划，高风险动作由确定性执行器完成。"},
    {"name": "InterviewOS", "subtitle": "AI Engineer Interview Workbench", "pipeline": ["Learn", "Code", "Interview", "Review"], "decision": "把题库、真实项目代码、Judge、AI 深挖和间隔复习连成一个闭环。"},
]


@router.get("/api/portfolio/{username}")
async def public_portfolio(username: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    owner = await db.scalar(select(User).where(User.username == username.strip().lower()))
    if not owner:
        raise HTTPException(404, "Portfolio not found")

    repos = (await db.scalars(
        select(Repository)
        .where(Repository.user_id == owner.id, Repository.is_public == 1)
        .order_by(Repository.synced_at.desc())
        .limit(6)
    )).all()
    repositories = [
        {"name": r.name, "provider": r.provider, "url": r.url, "commit": r.last_commit[:12], "files": r.file_count}
        for r in repos
    ]
    latest_score = await _latest_interview_score(db, owner)

    profile = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.user_id == owner.id))
    if not profile or profile.is_published != 1:
        # Unpublished: keep the exact legacy static shape (existing consumers
        # and privacy tests rely on it).
        return {
            "slug": owner.username,
            "name": owner.display_name or owner.username,
            "title": "AI / Agent Engineer",
            "summary": "Focused on structured AI agents, RAG, deterministic execution, FastAPI services and practical LLM systems.",
            "skills": ["Python", "FastAPI", "LangGraph", "RAG", "BGE-M3", "Redis", "PostgreSQL", "vLLM", "Docker"],
            "projects": _LEGACY_PROJECTS,
            "repositories": repositories,
            "latest_interview_score": latest_score,
        }

    projects = (await db.scalars(
        select(PortfolioProject)
        .where(PortfolioProject.user_id == owner.id, PortfolioProject.is_visible == 1)
        .order_by(PortfolioProject.order_index, PortfolioProject.id)
    )).all()
    public_repos = {r.id: r for r in repos}
    project_views = []
    for project in projects:
        repository = public_repos.get(project.repository_id) if project.repository_id else None
        view = _project_payload(project, repository)
        project_views.append({
            "name": view["title"],
            "subtitle": view["subtitle"],
            "description": view["description"],
            "architecture": view["architecture"],
            "decisions": view["decisions"],
            "tech_tags": view["tech_tags"],
            "link": view["link"],
            "repository": view["repository"],
        })

    return {
        "cms": True,
        "slug": owner.username,
        "name": profile.display_name or owner.display_name or owner.username,
        "title": profile.headline or "AI / Agent Engineer",
        "summary": profile.summary,
        "skills": _load_json_array(profile.skills_json),
        "resume_url": profile.resume_url,
        "social": _load_json_dict(profile.social_links_json),
        "projects": project_views,
        "repositories": repositories,
        "latest_interview_score": latest_score,
    }
