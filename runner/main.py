import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="InterviewOS Runner", version="1.1.0")


class RunRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    stdin: str = Field(default="", max_length=4000)


class TestCase(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    expected: Any


class JudgeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12000)
    function_name: str = Field(min_length=1, max_length=120)
    public_tests: list[TestCase] = Field(default_factory=list, max_length=20)
    hidden_tests: list[TestCase] = Field(default_factory=list, max_length=40)
    include_hidden: bool = True


def limits() -> None:
    # Development sandbox limits. For public internet exposure, replace this runner
    # with stronger isolation such as gVisor/Firecracker/Kubernetes sandbox workers.
    import resource  # POSIX only; imported lazily so the module also imports on Windows dev machines

    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    # RLIMIT_AS is intentionally not used: CPython can reserve a large virtual address space.
    # Docker mem_limit is the hard memory boundary for the runner container.
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 * 1024 * 1024, 1 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def _env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": "1.1.0",
        "sandbox": {
            "database": bool(SANDBOX_DATABASE_URL),
            "redis": bool(SANDBOX_REDIS_URL),
        },
    }


@app.post("/run")
def run(payload: RunRequest) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="interviewos-") as tmp:
        path = Path(tmp) / "main.py"
        path.write_text(payload.code, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(path)],
                input=payload.stdin,
                capture_output=True,
                text=True,
                timeout=3,
                cwd=tmp,
                env=_env(),
                preexec_fn=limits,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-12000:],
                "stderr": proc.stderr[-12000:],
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": 124,
                "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
                "stderr": "Execution timed out after 3 seconds.",
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }


def _judge_once(tmp: str, function_name: str, tests: list[TestCase], reveal: bool) -> dict:
    marker = "__INTERVIEWOS_JUDGE_RESULT__"
    tests_path = Path(tmp) / ("public_tests.json" if reveal else "hidden_tests.json")
    judge_path = Path(tmp) / ("judge_public.py" if reveal else "judge_hidden.py")
    tests_path.write_text(json.dumps([t.model_dump() for t in tests], ensure_ascii=False), encoding="utf-8")
    judge_source = f'''import json\nimport traceback\nimport importlib.util\nspec = importlib.util.spec_from_file_location('user_code', 'user_code.py')\nmodule = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\ntarget = getattr(module, {function_name!r})\n\nwith open({tests_path.name!r}, 'r', encoding='utf-8') as f:\n    tests = json.load(f)\n\ncases = []\nfor i, case in enumerate(tests):\n    try:\n        actual = target(*case.get('args', []), **case.get('kwargs', {{}}))\n        passed = actual == case.get('expected')\n        cases.append({{\n            'index': i + 1,\n            'passed': passed,\n            'args': case.get('args', []),\n            'kwargs': case.get('kwargs', {{}}),\n            'expected': case.get('expected'),\n            'actual': actual,\n            'error': '',\n        }})\n    except BaseException as exc:\n        cases.append({{\n            'index': i + 1,\n            'passed': False,\n            'args': case.get('args', []),\n            'kwargs': case.get('kwargs', {{}}),\n            'expected': case.get('expected'),\n            'actual': None,\n            'error': f'{{type(exc).__name__}}: {{exc}}',\n        }})\n\nprint({marker!r} + json.dumps(cases, ensure_ascii=False, default=repr))\n'''
    judge_path.write_text(judge_source, encoding="utf-8")
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(judge_path)],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=tmp,
            env=_env(),
            preexec_fn=limits,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "total": len(tests),
            "cases": [] if not reveal else [{"index": i + 1, "passed": False, "error": "Time limit exceeded"} for i in range(len(tests))],
            "runtime_error": "Time limit exceeded",
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    parsed: list[dict] | None = None
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(marker):
            try:
                parsed = json.loads(line[len(marker):])
            except json.JSONDecodeError:
                parsed = None
            break
    if parsed is None:
        error = (proc.stderr.strip() or "Judge could not import/execute the required function.")[-1200:]
        return {
            "passed": 0,
            "total": len(tests),
            "cases": [] if not reveal else [{"index": 1, "passed": False, "error": error}],
            "runtime_error": "Runtime error" if not reveal else error,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    passed = sum(1 for case in parsed if case.get("passed"))
    if reveal:
        safe_cases = parsed
    else:
        # Hidden inputs/expected outputs never leave the internal runner response.
        safe_cases = []
    return {
        "passed": passed,
        "total": len(parsed),
        "cases": safe_cases,
        "runtime_error": "",
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@app.post("/judge")
def judge(payload: JudgeRequest) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="interviewos-judge-") as tmp:
        (Path(tmp) / "user_code.py").write_text(payload.code, encoding="utf-8")
        public = _judge_once(tmp, payload.function_name, payload.public_tests, reveal=True)
        hidden = {"passed": 0, "total": 0, "cases": [], "runtime_error": "", "duration_ms": 0.0}
        if payload.include_hidden:
            hidden = _judge_once(tmp, payload.function_name, payload.hidden_tests, reveal=False)
        return {
            "public": public,
            "hidden": hidden,
            "all_passed": public["passed"] == public["total"] and (not payload.include_hidden or hidden["passed"] == hidden["total"]),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }


# --- v1.0 P1 sandbox playgrounds --------------------------------------------
#
# Interview-practice sandboxes. SQL and Redis run against dedicated sandbox
# services (SANDBOX_DATABASE_URL / SANDBOX_REDIS_URL, docker-compose services
# `sandbox-db` / `sandbox-redis` on the internal network) — never the main
# database or the main Redis. Each session key gets its own PostgreSQL schema
# (name derived from the unguessable key) and its own Redis database index
# (deterministic hash + collision probe through a marker key). The FastAPI
# playground reuses the subprocess isolation of /run.
#
# psycopg / redis are imported lazily inside the handlers so importing this
# module (e.g. from the backend test suite for guard-parity tests) works
# without them installed.

SANDBOX_DATABASE_URL = os.environ.get("SANDBOX_DATABASE_URL", "")
SANDBOX_REDIS_URL = os.environ.get("SANDBOX_REDIS_URL", "")

SQL_MAX_CHARS = 8000
SQL_STATEMENT_TIMEOUT_MS = 5000
SQL_MAX_ROWS = 200
SQL_MAX_COLUMNS = 50
SQL_MAX_CELL_CHARS = 200
SQL_SCHEMA_PREFIX = "s_"
SQL_MARKER_TABLE = "__sandbox_meta__"
SQL_SESSION_KEY_RE = re.compile(r"^[0-9a-f]{32}$")
SQL_SCHEMA_MAX_IDLE_HOURS = 24
SQL_GC_EVERY_N_REQUESTS = 25

REDIS_MAX_CHARS = 500
REDIS_MAX_ARGS = 16
REDIS_DATABASES = 64
REDIS_SESSION_TTL_SECONDS = 2 * 60 * 60
REDIS_SESSION_MARKER = "__interviewos_session__"
REDIS_COMMAND_NAME_RE = re.compile(r"^[A-Za-z]+$")
REDIS_MAX_LIST_ITEMS = 200
REDIS_MAX_VALUE_CHARS = 4000

FASTAPI_MAX_CHARS = 12000
FASTAPI_BODY_MAX_CHARS = 4000
FASTAPI_TIMEOUT_SECONDS = 6
FASTAPI_MARKER = "__INTERVIEWOS_FASTAPI_RESULT__"

# Statements that escape the session sandbox or attack the server. Privileges
# of the sandbox database user already block most of these — the guard turns
# silent permission errors into clear messages and adds defense in depth.
# Mirrored by backend/app/playground.py (parity-tested by the backend suite).
#
# String literals, quoted identifiers, comments and dollar-quoted blocks are
# blanked out before matching, so e.g. VALUES ('drop database joke') is not a
# false positive. Session-control verbs (SET / BEGIN / VACUUM / …) are only
# denied at statement start — `UPDATE t SET …` is legitimate mid-statement.
SQL_STRIP_RE = re.compile(
    r"""'(?:[^']|'')*'
      |"[^"]*"
      |--[^\n]*
      |/\*.*?\*/
      |\$([A-Za-z_]*)\$.*?\$\1\$
    """,
    re.DOTALL | re.VERBOSE,
)

SQL_DENY_RE = re.compile(
    r"""\b(?P<anywhere>
          drop\s+database | create\s+database | alter\s+database | alter\s+system
        | create\s+role | drop\s+role | alter\s+role
        | create\s+user | drop\s+user | alter\s+user
        | grant\b | revoke\b
        | create\s+schema | drop\s+schema
        | create\s+extension | drop\s+extension
        | create\s+tablespace | drop\s+tablespace
        | create\s+publication | drop\s+publication
        | create\s+subscription | drop\s+subscription
        | create\s+server | create\s+foreign\s+data\s+wrapper
        | import\s+foreign\s+schema
        | reassign\s+owned | drop\s+owned
        | copy\b[^;]*\bfrom\s+program
        | pg_read_file | pg_read_binary_file | pg_ls_dir
        | pg_terminate_backend | pg_cancel_backend | pg_reload_conf
        | pg_sleep | pg_sleep_for | pg_sleep_until
        | dblink | lo_import | lo_export
      )\b
      |
      (?:^|;)\s*(?P<statement_start>set | reset | listen | notify
                 | begin | commit | rollback | savepoint
                 | vacuum | checkpoint | reindex)\b""",
    re.IGNORECASE | re.VERBOSE,
)

REDIS_DENY_COMMANDS = frozenset(
    {
        "FLUSHALL", "FLUSHDB", "CONFIG", "DEBUG", "SHUTDOWN", "SAVE", "BGSAVE",
        "BGREWRITEAOF", "SCRIPT", "FUNCTION", "MODULE", "REPLICAOF", "SLAVEOF",
        "SWAPDB", "CLUSTER", "ACL", "FAILOVER", "RESET", "SELECT", "COPY",
        "MIGRATE", "RESTORE", "MOVE", "EVAL", "EVALSHA", "CLIENT", "MONITOR",
        "SUBSCRIBE", "UNSUBSCRIBE", "PSUBSCRIBE", "PUNSUBSCRIBE", "LATENCY",
        "MEMORY", "WAIT", "WAITAOF", "COMMAND",
    }
)

_gc_counter = {"n": 0}


class SandboxRejected(Exception):
    """User input rejected by the sandbox policy (reported to the client as a
    normal ok=false result, never a crash)."""


def sql_guard(sql: str) -> None:
    if len(sql) > SQL_MAX_CHARS:
        raise SandboxRejected(f"SQL batch exceeds {SQL_MAX_CHARS} characters")
    match = SQL_DENY_RE.search(SQL_STRIP_RE.sub(" ", sql))
    if match:
        keyword = (match.group("anywhere") or match.group("statement_start")).lower()
        raise SandboxRejected(f"statement rejected by the sandbox policy: {keyword!r} is not allowed")


def redis_guard(command: str) -> list[str]:
    if len(command) > REDIS_MAX_CHARS:
        raise SandboxRejected(f"command exceeds {REDIS_MAX_CHARS} characters")
    tokens = shlex.split(command)
    if not tokens:
        raise SandboxRejected("empty command")
    if len(tokens) > REDIS_MAX_ARGS:
        raise SandboxRejected(f"command exceeds {REDIS_MAX_ARGS} arguments")
    if not REDIS_COMMAND_NAME_RE.match(tokens[0]):
        raise SandboxRejected("command name must be alphabetic (arguments are passed as separate parameters)")
    name = tokens[0].upper()
    if name in REDIS_DENY_COMMANDS:
        raise SandboxRejected(f"command {name} is not allowed in the sandbox")
    return tokens


class PgSessionRequest(BaseModel):
    session_key: str = Field(pattern=r"^[0-9a-f]{32}$")


class PgSqlRequest(PgSessionRequest):
    sql: str = Field(min_length=1, max_length=SQL_MAX_CHARS)


class PgRedisRequest(PgSessionRequest):
    command: str = Field(min_length=1, max_length=REDIS_MAX_CHARS)


class PgFastApiRequest(BaseModel):
    code: str = Field(min_length=1, max_length=FASTAPI_MAX_CHARS)
    method: str = Field(pattern=r"^(GET|POST|PUT|PATCH|DELETE)$")
    path: str = Field(min_length=1, max_length=300, pattern=r"^/[!-~]*$")
    body: str = Field(default="", max_length=FASTAPI_BODY_MAX_CHARS)


def _session_schema(session_key: str) -> str:
    return SQL_SCHEMA_PREFIX + session_key[:16]


def _describe_result(cursor: Any) -> dict:
    if cursor.description is None:
        return {"columns": [], "rows": [], "rowcount": cursor.rowcount, "truncated": False, "error": ""}
    columns = [column.name for column in cursor.description][:SQL_MAX_COLUMNS]
    fetched = cursor.fetchmany(SQL_MAX_ROWS + 1)
    truncated = len(fetched) > SQL_MAX_ROWS or len(cursor.description) > SQL_MAX_COLUMNS
    rows = [[_cell(value) for value in row[:SQL_MAX_COLUMNS]] for row in fetched[:SQL_MAX_ROWS]]
    return {"columns": columns, "rows": rows, "rowcount": cursor.rowcount, "truncated": truncated, "error": ""}


def _cell(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= SQL_MAX_CELL_CHARS else text[:SQL_MAX_CELL_CHARS] + "…"


def _open_session_schema(cursor: Any, session_key: str) -> str:
    if not SQL_SESSION_KEY_RE.match(session_key):
        raise SandboxRejected("invalid session key")
    schema = _session_schema(session_key)
    cursor.execute(f"SET statement_timeout = {int(SQL_STATEMENT_TIMEOUT_MS)}")
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    cursor.execute(
        f'CREATE TABLE IF NOT EXISTS "{schema}"."{SQL_MARKER_TABLE}" '
        "(session_key text PRIMARY KEY, last_seen timestamptz NOT NULL)"
    )
    cursor.execute(
        f'INSERT INTO "{schema}"."{SQL_MARKER_TABLE}" (session_key, last_seen) '
        "VALUES (%s, now()) ON CONFLICT (session_key) DO UPDATE SET last_seen = now()",
        (session_key,),
    )
    cursor.execute(f'SET search_path TO "{schema}"')
    return schema


def _gc_sandboxes(cursor: Any) -> None:
    """Drop playground schemas idle beyond the retention window. Called
    opportunistically (every SQL_GC_EVERY_N_REQUESTS-th request) and always
    best-effort — GC must never fail a user request."""
    cursor.execute(
        "SELECT nspname FROM pg_catalog.pg_namespace "
        r"WHERE nspname LIKE 's\_%' ESCAPE '\' AND length(nspname) = 18"
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SQL_SCHEMA_MAX_IDLE_HOURS)
    for (nspname,) in cursor.fetchall():
        if not SQL_SESSION_KEY_RE.match(nspname[2:]):
            continue
        try:
            cursor.execute(f'SELECT max(last_seen) FROM "{nspname}"."{SQL_MARKER_TABLE}"')
            row = cursor.fetchone()
            if row is None or row[0] is None or row[0] < cutoff:
                cursor.execute(f'DROP SCHEMA "{nspname}" CASCADE')
        except Exception:  # noqa: BLE001 — a broken schema must not stop the sweep
            continue


def _maybe_gc(cursor: Any) -> None:
    _gc_counter["n"] += 1
    if _gc_counter["n"] % SQL_GC_EVERY_N_REQUESTS != 1:
        return
    try:
        _gc_sandboxes(cursor)
    except Exception:  # noqa: BLE001
        pass


@app.post("/pg/sql")
def pg_sql(payload: PgSqlRequest) -> dict:
    """Execute a SQL batch in the session's isolated schema. The whole batch
    runs as one implicit transaction: any failing statement rolls the batch
    back, so a fixed re-run starts from the last committed state."""
    started = time.perf_counter()

    def result(ok: bool, statements: list[dict], error: str) -> dict:
        return {"ok": ok, "statements": statements, "duration_ms": round((time.perf_counter() - started) * 1000, 1), "error": error}

    if not SANDBOX_DATABASE_URL:
        return result(False, [], "sandbox database is not configured (SANDBOX_DATABASE_URL)")
    try:
        sql_guard(payload.sql)
    except SandboxRejected as exc:
        return result(False, [], str(exc))

    import psycopg  # lazy: heavy dependency, not needed to import this module

    try:
        with psycopg.connect(SANDBOX_DATABASE_URL, autocommit=True, connect_timeout=3) as conn:
            with conn.cursor() as cursor:
                _maybe_gc(cursor)
                _open_session_schema(cursor, payload.session_key)
                cursor.execute(payload.sql)
                statements: list[dict] = []
                while True:
                    statements.append(_describe_result(cursor))
                    if not cursor.nextset():
                        break
                return result(True, statements, "")
    except SandboxRejected as exc:
        return result(False, [], str(exc))
    except psycopg.Error as exc:
        return result(False, [], str(exc).strip()[:500] or type(exc).__name__)
    except Exception as exc:  # noqa: BLE001 — user SQL must never 500 the runner
        return result(False, [], f"{type(exc).__name__}: {exc}"[:500])


def _redis_client(db: int) -> Any:
    import redis  # lazy: heavy dependency

    # redis-py's from_url lets URL options override kwargs, so a URL ending in
    # /0 would pin every client to db 0 no matter what db= says. Parse the URL
    # and build the client explicitly instead.
    parsed = urllib.parse.urlparse(SANDBOX_REDIS_URL)
    return redis.Redis(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=parsed.username,
        password=parsed.password,
        db=db,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )


def _redis_session_db(session_key: str) -> int:
    """Resolve the session's Redis database index: deterministic hash first,
    then linear probe. A marker key claims the database for the session and
    carries the idle TTL; an unclaimed database is flushed before claiming so
    stale keys never leak into a new session."""
    base = int.from_bytes(hashlib.blake2b(session_key.encode(), digest_size=4).digest(), "big")
    for offset in range(REDIS_DATABASES - 1):
        index = base % (REDIS_DATABASES - 1) + 1
        base += 1
        probe = _redis_client(index)
        marker = probe.get(REDIS_SESSION_MARKER)
        if marker == session_key:
            probe.expire(REDIS_SESSION_MARKER, REDIS_SESSION_TTL_SECONDS)
            return index
        if marker is None:
            probe.flushdb()
            if probe.set(REDIS_SESSION_MARKER, session_key, ex=REDIS_SESSION_TTL_SECONDS, nx=True):
                return index
    raise SandboxRejected("no free sandbox redis database; try again later")


def _redis_value(value: Any, state: dict) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        if len(value) > REDIS_MAX_VALUE_CHARS:
            state["truncated"] = True
            return value[:REDIS_MAX_VALUE_CHARS] + "…"
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > REDIS_MAX_LIST_ITEMS:
            state["truncated"] = True
        return [_redis_value(item, state) for item in value[:REDIS_MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        items = list(value.items())
        if len(items) > REDIS_MAX_LIST_ITEMS:
            state["truncated"] = True
        return {str(key): _redis_value(item, state) for key, item in items[:REDIS_MAX_LIST_ITEMS]}
    return str(value)[:REDIS_MAX_VALUE_CHARS]


@app.post("/pg/redis")
def pg_redis(payload: PgRedisRequest) -> dict:
    """Execute one Redis command inside the session's isolated database
    index. Arguments travel as separate protocol parameters, so user input can
    never inject additional commands."""
    started = time.perf_counter()

    def result(ok: bool, command_result: dict | None, error: str) -> dict:
        return {"ok": ok, "result": command_result, "duration_ms": round((time.perf_counter() - started) * 1000, 1), "error": error}

    if not SANDBOX_REDIS_URL:
        return result(False, None, "sandbox redis is not configured (SANDBOX_REDIS_URL)")
    try:
        tokens = redis_guard(payload.command)
    except SandboxRejected as exc:
        return result(False, None, str(exc))

    import redis  # lazy: heavy dependency

    try:
        client = _redis_client(_redis_session_db(payload.session_key))
        raw = client.execute_command(*tokens)
        state = {"truncated": False}
        value = _redis_value(raw, state)
        return result(True, {"type": type(raw).__name__, "value": value, "truncated": state["truncated"]}, "")
    except SandboxRejected as exc:
        return result(False, None, str(exc))
    except redis.RedisError as exc:
        return result(False, None, str(exc).strip()[:500] or type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        return result(False, None, f"{type(exc).__name__}: {exc}"[:500])


_FASTAPI_DRIVER = """
import asyncio
import importlib.util
import json
import os

marker = "__INTERVIEWOS_FASTAPI_RESULT__"
spec = importlib.util.spec_from_file_location("user_app", "user_app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

import httpx
from fastapi import FastAPI

app = getattr(module, "app", None)
if not isinstance(app, FastAPI):
    found = [value for value in vars(module).values() if isinstance(value, FastAPI)]
    app = found[0] if len(found) == 1 else None
if app is None:
    print(marker + json.dumps({"ok": False, "error": "no FastAPI app found: define one, e.g. app = FastAPI()"}))
    raise SystemExit(0)

body = None
if os.path.exists("body.json"):
    with open("body.json", encoding="utf-8") as handle:
        text = handle.read().strip()
    if text:
        body = json.loads(text)

# httpx.ASGITransport instead of starlette's TestClient: TestClient needs an
# extra thread for its blocking portal, which RLIMIT_NPROC can forbid inside
# the sandbox; the ASGI transport serves the app in-process on one thread.
async def _request():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(__METHOD__, __PATH__, json=body)

response = asyncio.run(_request())
print(marker + json.dumps({
    "ok": True,
    "status": response.status_code,
    "headers": {key: value for key, value in response.headers.items()
                if key.lower() not in ("content-length", "content-encoding", "transfer-encoding", "server", "date")},
    "body": response.text[:20000],
}))
"""


@app.post("/pg/fastapi")
def pg_fastapi(payload: PgFastApiRequest) -> dict:
    """Run a user FastAPI app in an isolated subprocess and issue one request
    against it through fastapi.testclient. Same isolation as /run: -I mode,
    resource limits, tmpfs working directory, hard timeout."""
    started = time.perf_counter()

    def result(ok: bool, error: str, status: int = 0, headers: dict | None = None, body: str = "", stdout: str = "", stderr: str = "") -> dict:
        return {
            "ok": ok, "error": error, "status": status, "headers": headers or {},
            "body": body, "stdout": stdout[-8000:], "stderr": stderr[-8000:],
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    if payload.body.strip():
        try:
            json.loads(payload.body)
        except json.JSONDecodeError as exc:
            return result(False, f"request body is not valid JSON: {exc.msg}")

    driver = _FASTAPI_DRIVER.replace("__METHOD__", repr(payload.method)).replace("__PATH__", repr(payload.path))
    with tempfile.TemporaryDirectory(prefix="interviewos-fastapi-") as tmp:
        (Path(tmp) / "user_app.py").write_text(payload.code, encoding="utf-8")
        (Path(tmp) / "driver.py").write_text(driver, encoding="utf-8")
        if payload.body.strip():
            (Path(tmp) / "body.json").write_text(payload.body, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "driver.py"],
                capture_output=True, text=True, timeout=FASTAPI_TIMEOUT_SECONDS,
                cwd=tmp, env=_env(), preexec_fn=limits,
            )
        except subprocess.TimeoutExpired:
            return result(False, f"app did not answer within {FASTAPI_TIMEOUT_SECONDS} seconds (infinite loop or blocking startup?)")

    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(FASTAPI_MARKER):
            try:
                parsed = json.loads(line[len(FASTAPI_MARKER):])
            except json.JSONDecodeError:
                break
            if parsed.pop("ok", False):
                return result(True, "", **parsed)
            return result(False, str(parsed.get("error", "app failed to start")), stdout=proc.stdout, stderr=proc.stderr)
    error = (proc.stderr.strip() or proc.stdout.strip() or "the app could not be imported")[:500]
    return result(False, error, stdout=proc.stdout, stderr=proc.stderr)


@app.post("/pg/reset")
def pg_reset(payload: PgSessionRequest) -> dict:
    """Wipe the session's SQL schema and Redis database back to a clean
    sandbox (used by the frontend reset button and on session expiry)."""
    reset_sql = reset_redis = False
    if SANDBOX_DATABASE_URL:
        import psycopg

        try:
            with psycopg.connect(SANDBOX_DATABASE_URL, autocommit=True, connect_timeout=3) as conn:
                with conn.cursor() as cursor:
                    schema = _session_schema(payload.session_key)
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    _open_session_schema(cursor, payload.session_key)
                    reset_sql = True
        except psycopg.Error:
            reset_sql = False
    if SANDBOX_REDIS_URL:
        try:
            client = _redis_client(_redis_session_db(payload.session_key))
            client.flushdb()
            client.set(REDIS_SESSION_MARKER, payload.session_key, ex=REDIS_SESSION_TTL_SECONDS)
            reset_redis = True
        except Exception:  # noqa: BLE001
            reset_redis = False
    return {"ok": reset_sql or reset_redis, "reset_sql": reset_sql, "reset_redis": reset_redis}
