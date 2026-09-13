"""v1.0 P1 Playgrounds: backend-side sandbox policy mirror.

The runner (runner/main.py) is the authoritative security boundary for the
SQL / Redis / FastAPI sandboxes. The backend re-validates with the exact same
deny lists so dangerous input is rejected before the runner is even reached
(defense in depth) and so the API layer can answer with clean 400s instead of
proxied sandbox rejections.

tests/test_playgrounds.py imports runner/main.py directly and asserts this
mirror stays in sync — edit both files together.
"""
from __future__ import annotations

import re
import shlex

from .config import settings

# Mirrors runner/main.py byte-for-byte (parity-tested by tests/test_playgrounds.py):
# literals / quoted identifiers / comments / dollar-quotes are blanked out before
# matching, session-control verbs are only denied at statement start.
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

REDIS_COMMAND_NAME_RE = re.compile(r"^[A-Za-z]+$")

PLAYGROUND_KINDS = ("sql", "redis")

SAMPLE_SNIPPETS: dict[str, dict[str, str]] = {
    "sql": {
        "title": "候选人表：建表 / 插入 / 排序查询",
        "code": (
            "CREATE TABLE candidates (\n"
            "  id serial PRIMARY KEY,\n"
            "  name text NOT NULL,\n"
            "  score int NOT NULL\n"
            ");\n"
            "\n"
            "INSERT INTO candidates (name, score) VALUES ('Alice', 88), ('Bob', 72), ('Carol', 95);\n"
            "\n"
            "SELECT name, score FROM candidates ORDER BY score DESC;"
        ),
    },
    "redis": {
        "title": "缓存一个候选人对象",
        "code": 'SET candidate:1 \'{"name":"Alice","score":88}\'',
    },
    "fastapi": {
        "title": "最小的 FastAPI 应用",
        "code": (
            "from fastapi import FastAPI\n"
            "\n"
            "app = FastAPI()\n"
            "\n"
            "\n"
            "@app.get(\"/hello\")\n"
            "def hello(name: str = \"world\"):\n"
            "    return {\"message\": f\"hello {name}\"}\n"
        ),
    },
}


class SandboxPolicyError(ValueError):
    """Input rejected by the backend mirror of the sandbox policy."""


def sql_guard(sql: str) -> None:
    if len(sql) > settings.playground_sql_max_chars:
        raise SandboxPolicyError(f"SQL batch exceeds {settings.playground_sql_max_chars} characters")
    match = SQL_DENY_RE.search(SQL_STRIP_RE.sub(" ", sql))
    if match:
        keyword = (match.group("anywhere") or match.group("statement_start")).lower()
        raise SandboxPolicyError(f"statement rejected by the sandbox policy: {keyword!r} is not allowed")


def redis_guard(command: str) -> None:
    if len(command) > settings.playground_redis_max_chars:
        raise SandboxPolicyError(f"command exceeds {settings.playground_redis_max_chars} characters")
    tokens = shlex.split(command)
    if not tokens:
        raise SandboxPolicyError("empty command")
    if not REDIS_COMMAND_NAME_RE.match(tokens[0]):
        raise SandboxPolicyError("command name must be alphabetic")
    name = tokens[0].upper()
    if name in REDIS_DENY_COMMANDS:
        raise SandboxPolicyError(f"command {name} is not allowed in the sandbox")
