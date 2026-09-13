"""v1.0 P1 Playgrounds: sandbox session lifecycle, backend-side guard mirror,
runner proxying and cross-user isolation. Runner HTTP calls are monkeypatched
(RunnerStub); guard parity is verified by importing runner/main.py directly —
the suite never needs a live sandbox database, redis or the runner service.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

from app import playground, playground_routes
from app.playground import SandboxPolicyError
from tests.conftest import DB_PATH

RUNNER_DIR = Path(__file__).resolve().parents[2] / "runner"
if str(RUNNER_DIR) not in sys.path:
    sys.path.insert(0, str(RUNNER_DIR))

import main as runner_main  # noqa: E402  (runner service module, heavy deps are lazy)


class RunnerStub:
    """Replace playground_routes._runner_post; records every call."""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.response = response if response is not None else {"ok": True}
        self.error = error

    async def __call__(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        if self.error is not None:
            raise self.error
        return self.response


def db_rows(sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def db_exec(sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def make_session(client, headers: dict, kind: str = "sql") -> int:
    response = client.post("/api/playground/sessions", json={"kind": kind}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


# --- guard parity: backend mirror must match the runner boundary ------------


def test_sql_deny_regex_matches_runner():
    assert playground.SQL_DENY_RE.pattern == runner_main.SQL_DENY_RE.pattern
    assert playground.SQL_STRIP_RE.pattern == runner_main.SQL_STRIP_RE.pattern


def test_redis_deny_set_matches_runner():
    assert playground.REDIS_DENY_COMMANDS == runner_main.REDIS_DENY_COMMANDS


# --- runner-side guards (unit, imported from runner/main.py) ----------------


@pytest.mark.parametrize(
    "sql",
    [
        "DROP DATABASE sandbox",
        "drop database sandbox;",
        "CREATE ROLE admin SUPERUSER",
        "GRANT ALL ON SCHEMA public TO public",
        "SELECT pg_sleep(30)",
        "SET search_path TO public",
        "COPY t FROM PROGRAM 'rm -rf /'",
        "BEGIN; SELECT 1;",
        "SELECT * FROM dblink('host=x', 'select 1') AS t(x int)",
        "/* hidden */ DROP DATABASE sandbox",
        "SELECT 1; SET statement_timeout = 0",
        "SELECT 'plain' ; VACUUM t",
    ],
)
def test_runner_sql_guard_rejects_dangerous_statements(sql):
    with pytest.raises(runner_main.SandboxRejected):
        runner_main.sql_guard(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "CREATE TABLE t (id serial PRIMARY KEY, name text)",
        "INSERT INTO t (name) VALUES ('drop database joke')",  # string literal: fine
        "INSERT INTO logs (msg) VALUES ('it''s a -- comment, not SQL')",
        "SELECT name FROM candidates WHERE score > 80 ORDER BY name",
        "UPDATE t SET name = 'alice' WHERE id = 1",
        "CREATE INDEX idx_t_name ON t (name)",
        "EXPLAIN SELECT * FROM t",
        "SELECT * FROM settings WHERE reset IS NOT NULL",  # keyword-like identifiers: fine
    ],
)
def test_runner_sql_guard_allows_normal_statements(sql):
    runner_main.sql_guard(sql)


@pytest.mark.parametrize(
    "command",
    [
        "FLUSHALL",
        "flushdb",
        "CONFIG GET maxmemory",
        "SHUTDOWN",
        "EVAL \"return 1\" 0",
        "SELECT 0",
        "SCRIPT LOAD x",
        "MIGRATE host 6379 key 0 1000",
    ],
)
def test_runner_redis_guard_rejects_dangerous_commands(command):
    with pytest.raises(runner_main.SandboxRejected):
        runner_main.redis_guard(command)


def test_runner_redis_guard_parses_and_allows_normal_commands():
    assert runner_main.redis_guard("SET greeting 'hello world'") == ["SET", "greeting", "hello world"]
    assert runner_main.redis_guard("get greeting") == ["get", "greeting"]
    with pytest.raises(runner_main.SandboxRejected):
        runner_main.redis_guard("HSET " + " ".join(f"f{i} v{i}" for i in range(20)))


def test_runner_session_key_is_strictly_validated():
    request = runner_main.PgSessionRequest.model_validate({"session_key": "a" * 32})
    assert request.session_key == "a" * 32
    with pytest.raises(ValueError):
        runner_main.PgSessionRequest.model_validate({"session_key": "not-hex!"})
    with pytest.raises(ValueError):
        runner_main.PgSessionRequest.model_validate({"session_key": "abc"})


# --- backend guard mirror (unit) ---------------------------------------------


def test_backend_sql_guard_rejects_and_allows():
    with pytest.raises(SandboxPolicyError):
        playground.sql_guard("DROP DATABASE sandbox")
    with pytest.raises(SandboxPolicyError):
        playground.sql_guard("SELECT pg_sleep(10)")
    playground.sql_guard("SELECT 1")


def test_backend_redis_guard_rejects_and_allows():
    with pytest.raises(SandboxPolicyError):
        playground.redis_guard("FLUSHALL")
    with pytest.raises(SandboxPolicyError):
        playground.redis_guard("config get maxmemory")
    playground.redis_guard("SET k v")


# --- API surface --------------------------------------------------------------


def test_playground_routes_require_authentication(client):
    assert client.get("/api/playground/meta").status_code == 200  # public static info
    assert client.post("/api/playground/sessions", json={"kind": "sql"}).status_code == 401
    assert client.post("/api/playground/sql", json={"session_id": 1, "sql": "SELECT 1"}).status_code == 401
    assert client.post("/api/playground/redis", json={"session_id": 1, "command": "PING"}).status_code == 401
    assert client.post("/api/playground/fastapi", json={"code": "x", "method": "GET", "path": "/"}).status_code == 401
    assert client.post("/api/playground/reset", json={"session_id": 1}).status_code == 401


def test_playground_meta_shape(client):
    meta = client.get("/api/playground/meta").json()
    assert meta["kinds"] == ["sql", "redis", "fastapi"]
    assert meta["limits"]["sql_max_chars"] == 8000
    assert set(meta["samples"]) == {"sql", "redis", "fastapi"}
    assert "FLUSHALL" in meta["policy"]["redis"]


def test_create_session_stores_unguessable_key(client, make_user):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    row = sqlite3.connect(DB_PATH).execute(
        "SELECT session_key, kind, user_id FROM playground_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    assert row is not None
    session_key, kind, user_id = row
    assert re.fullmatch(r"[0-9a-f]{32}", session_key)
    assert kind == "sql"
    assert user_id == user["user"]["id"]


def test_create_session_rejects_unknown_kind(client, make_user):
    user = make_user()
    response = client.post("/api/playground/sessions", json={"kind": "fastapi"}, headers=user["headers"])
    assert response.status_code == 422


def test_sql_playground_proxies_session_key_and_result(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    stub = RunnerStub({"ok": True, "statements": [{"columns": ["?column?"], "rows": [[1]], "rowcount": 1, "truncated": False, "error": ""}], "duration_ms": 3.2, "error": ""})
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["statements"][0]["rows"] == [[1]]
    assert stub.calls == [("/pg/sql", {"session_key": stub.calls[0][1]["session_key"], "sql": "SELECT 1"})]
    assert re.fullmatch(r"[0-9a-f]{32}", stub.calls[0][1]["session_key"])


def test_sql_dangerous_statement_blocked_before_runner(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "DROP DATABASE sandbox"}, headers=user["headers"])
    assert response.status_code == 400
    assert "sandbox policy" in response.json()["detail"]
    assert stub.calls == []


def test_redis_playground_proxies_and_blocks_dangerous_commands(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "redis")
    stub = RunnerStub({"ok": True, "result": {"type": "str", "value": "OK", "truncated": False}, "duration_ms": 1.0, "error": ""})
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    ok = client.post("/api/playground/redis", json={"session_id": session_id, "command": "SET greeting hello"}, headers=user["headers"])
    assert ok.status_code == 200
    assert ok.json()["result"]["value"] == "OK"
    assert stub.calls[0][0] == "/pg/redis"

    blocked = client.post("/api/playground/redis", json={"session_id": session_id, "command": "FLUSHALL"}, headers=user["headers"])
    assert blocked.status_code == 400
    assert len(stub.calls) == 1  # FLUSHALL never reached the runner


def test_session_cannot_be_used_by_another_user(client, make_user, monkeypatch):
    alice, eve = make_user(), make_user()
    session_id = make_session(client, alice["headers"], "sql")
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=eve["headers"])
    assert response.status_code == 404
    response = client.post("/api/playground/reset", json={"session_id": session_id}, headers=eve["headers"])
    assert response.status_code == 404
    assert stub.calls == []


def test_session_kind_must_match_endpoint(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "redis")
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=user["headers"])
    assert response.status_code == 400
    assert "redis" in response.json()["detail"]
    assert stub.calls == []


def test_expired_session_returns_410(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE playground_sessions SET expires_at = '2000-01-01 00:00:00' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=user["headers"])
    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()
    assert stub.calls == []


def test_missing_session_returns_404(client, make_user, monkeypatch):
    user = make_user()
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)
    response = client.post("/api/playground/sql", json={"session_id": 999, "sql": "SELECT 1"}, headers=user["headers"])
    assert response.status_code == 404
    assert stub.calls == []


def test_fastapi_playground_validation_and_passthrough(client, make_user, monkeypatch):
    user = make_user()
    stub = RunnerStub({"ok": True, "error": "", "status": 200, "headers": {"content-type": "application/json"}, "body": '{"message":"hello world"}', "stdout": "", "stderr": "", "duration_ms": 120.0})
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    bad_method = client.post("/api/playground/fastapi", json={"code": "app=1", "method": "TRACE", "path": "/"}, headers=user["headers"])
    assert bad_method.status_code == 422
    bad_path = client.post("/api/playground/fastapi", json={"code": "app=1", "method": "GET", "path": "no-slash"}, headers=user["headers"])
    assert bad_path.status_code == 422
    assert stub.calls == []

    ok = client.post(
        "/api/playground/fastapi",
        json={"code": "from fastapi import FastAPI\napp = FastAPI()", "method": "GET", "path": "/hello", "body": ""},
        headers=user["headers"],
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == 200
    path, payload = stub.calls[0]
    assert path == "/pg/fastapi"
    assert payload["method"] == "GET" and payload["path"] == "/hello"


def test_fastapi_playground_rejects_oversized_code(client, make_user, monkeypatch):
    user = make_user()
    stub = RunnerStub()
    monkeypatch.setattr(playground_routes, "_runner_post", stub)
    response = client.post(
        "/api/playground/fastapi",
        json={"code": "x" * (playground_routes.settings.playground_fastapi_max_chars + 1), "method": "GET", "path": "/"},
        headers=user["headers"],
    )
    assert response.status_code == 400
    assert stub.calls == []


def test_runner_outage_maps_to_502(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    monkeypatch.setattr(playground_routes, "_runner_post", RunnerStub(error=httpx.ConnectError("refused")))
    response = client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=user["headers"])
    assert response.status_code == 502
    assert "Sandbox unavailable" in response.json()["detail"]


def test_reset_requires_ownership_and_proxies(client, make_user, monkeypatch):
    alice = make_user()
    session_id = make_session(client, alice["headers"], "redis")
    stub = RunnerStub({"ok": True, "reset_sql": False, "reset_redis": True})
    monkeypatch.setattr(playground_routes, "_runner_post", stub)

    response = client.post("/api/playground/reset", json={"session_id": session_id}, headers=alice["headers"])
    assert response.status_code == 200
    assert response.json() == {"session_id": session_id, "kind": "redis", "ok": True, "reset_sql": False, "reset_redis": True}
    assert stub.calls[0][0] == "/pg/reset"

    missing = client.post("/api/playground/reset", json={"session_id": 424242}, headers=alice["headers"])
    assert missing.status_code == 404


def test_session_usage_updates_last_used(client, make_user, monkeypatch):
    user = make_user()
    session_id = make_session(client, user["headers"], "sql")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE playground_sessions SET last_used_at = '2000-01-01 00:00:00' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    monkeypatch.setattr(playground_routes, "_runner_post", RunnerStub({"ok": True}))

    client.post("/api/playground/sql", json={"session_id": session_id, "sql": "SELECT 1"}, headers=user["headers"])
    row = sqlite3.connect(DB_PATH).execute("SELECT last_used_at FROM playground_sessions WHERE id = ?", (session_id,)).fetchone()
    assert row[0] != "2000-01-01 00:00:00"
