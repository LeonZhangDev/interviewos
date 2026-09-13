"""Shared helpers for the question CMS: title-similarity duplicate detection
and unique slug generation. Used by the CRUD endpoints in main.py and the
import preview in v07.py."""
from __future__ import annotations

import difflib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Question


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip()).strip("-").lower()
    return normalized[:105] or uuid.uuid4().hex[:12]


def normalize_title(value: str) -> str:
    return " ".join(value.strip().casefold().split())


async def find_duplicates(
    db: AsyncSession,
    title: str,
    exclude_id: int | None = None,
    threshold: float = 0.75,
    limit: int = 5,
) -> list[dict]:
    """Title-similarity duplicate candidates (exact normalized match or
    SequenceMatcher ratio >= threshold). Titles are short, so a full scan of
    the active question bank is acceptable for this local-first app."""
    normalized = normalize_title(title)
    if not normalized:
        return []
    rows = (await db.scalars(select(Question).where(Question.archived == 0))).all()
    hits: list[dict] = []
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        candidate = normalize_title(row.title)
        ratio = difflib.SequenceMatcher(None, normalized, candidate).ratio()
        if candidate == normalized or ratio >= threshold:
            hits.append({
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "similarity": round(ratio, 3),
            })
    hits.sort(key=lambda x: (-x["similarity"], x["id"]))
    return hits[:limit]


async def unique_slug(db: AsyncSession, category: str, title: str) -> str:
    base = slugify(f"{category}-{title}")[:120]
    existing = set((await db.scalars(select(Question.slug))).all())
    slug = base
    suffix = 2
    while slug in existing:
        slug = f"{base[:112]}-{suffix}"
        suffix += 1
    return slug
