"""Shared fixtures for the InterviewOS backend test suite.

The suite runs entirely offline: SQLite (aiosqlite) via Alembic migrations,
a closed Redis port (every cache call fails fast and is swallowed by the
app), no LLM provider and no Runner service.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TMP = Path(tempfile.mkdtemp(prefix="interviewos-tests-"))
DB_PATH = TEST_TMP / "test.db"
RECORDINGS_DIR = TEST_TMP / "recordings"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
# Closed local port: redis-py raises ConnectionRefused immediately instead of
# hanging, and every endpoint already tolerates cache failures.
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["AUTH_SECRET"] = "test-secret-do-not-use-in-production"
os.environ["AUTH_TOKEN_MINUTES"] = "60"
os.environ["AUTH_REFRESH_DAYS"] = "14"
os.environ["RECORDINGS_DIR"] = str(RECORDINGS_DIR)
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""
# v1.0 Git provider OAuth: fake client credentials + a dedicated encryption
# key so the encrypted-token tests do not depend on AUTH_SECRET. The suite
# never contacts real providers (httpx calls are monkeypatched per test).
os.environ["GITHUB_CLIENT_ID"] = "test-github-client-id"
os.environ["GITHUB_CLIENT_SECRET"] = "test-github-client-secret"
os.environ["GITEE_CLIENT_ID"] = "test-gitee-client-id"
os.environ["GITEE_CLIENT_SECRET"] = "test-gitee-client-secret"
os.environ["OAUTH_ENCRYPTION_KEY"] = "test-oauth-encryption-key-do-not-use"
os.environ["OAUTH_REDIRECT_BASE"] = "http://localhost:5173"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Apply the full Alembic chain once. Every API test therefore runs
    against the migrated schema, not Base.metadata.create_all."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


def wipe_database() -> None:
    """Delete every model row (alembic_version untouched) so each test starts
    from a clean instance. Startup re-seeds the shared question bank."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(f'DELETE FROM "{table.name}"')
        conn.commit()
    finally:
        conn.close()


def db_insert(sql: str, params: tuple = ()) -> int:
    """Raw row insert for arranging legacy / cross-user fixture data."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        cursor = conn.execute(sql, params)
        conn.commit()
        return int(cursor.lastrowid or 0)
    finally:
        conn.close()


def db_scalar(sql: str, params: tuple = ()):
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


@pytest.fixture()
def client():
    wipe_database()
    with TestClient(app) as test_client:
        yield test_client
        wipe_database()


@pytest.fixture()
def make_user(client):
    counter = {"n": 0}

    def _make(username: str | None = None, password: str = "secret-pass-123") -> dict:
        counter["n"] += 1
        name = username or f"user{counter['n']}"
        response = client.post(
            "/api/auth/register",
            json={
                "username": name,
                "email": f"{name}@example.com",
                "password": password,
                "display_name": name.title(),
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        return {
            "username": name,
            "password": password,
            "user": data["user"],
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"},
        }

    return _make
