from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = {"github.com", "www.github.com", "gitee.com", "www.gitee.com"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next", "coverage", ".idea"}
TEXT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".md", ".sql", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".env", ".sh", ".go", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".rs", ".html", ".css",
}
LANGUAGE = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript React", ".js": "JavaScript", ".jsx": "JavaScript React",
    ".vue": "Vue", ".md": "Markdown", ".sql": "SQL", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".sh": "Shell", ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".c": "C",
    ".h": "C/C++ Header", ".cpp": "C++", ".hpp": "C++ Header", ".rs": "Rust", ".html": "HTML", ".css": "CSS",
}

KNOWLEDGE_RULES = {
    "FastAPI": ["fastapi", "apirouter", "depends(", "@app.", "@router."],
    "Pydantic": ["pydantic", "basemodel", "field("],
    "SQLAlchemy": ["sqlalchemy", "asyncsession", "mapped_column", "select("],
    "asyncio": ["asyncio", "async def", "await ", "gather("],
    "Redis": ["redis", "cache", "ttl"],
    "RAG": ["retriev", "embedding", "vector", "faiss", "rerank", "bge-m3"],
    "LangGraph / Agent": ["langgraph", "stategraph", "tool_call", "agent", "approval"],
    "LlamaIndex": ["llama_index", "llamaindex"],
    "LLM Serving": ["vllm", "chat/completions", "openai", "deepseek"],
    "Testing": ["pytest", "unittest", "test_", "assert "],
    "Docker": ["dockerfile", "docker compose", "docker-compose"],
    "Database": ["postgres", "mysql", "transaction", "join ", "index"],
    "Security": ["token", "jwt", "rbac", "permission", "audit", "hashlib"],
}

QUESTION_BY_TOPIC = {
    "FastAPI": ["为什么这里适合使用依赖注入而不是把逻辑直接写进路由？", "这段 FastAPI 代码在并发请求下有哪些生命周期问题？"],
    "SQLAlchemy": ["这里的 Session/事务边界在哪里？为什么不能跨并发任务共享？", "这段 ORM 访问是否可能出现 N+1 或隐式查询？"],
    "asyncio": ["这里在哪些 await 点会让出执行权？共享状态是否可能发生竞态？", "如果内部调用阻塞函数，会怎样影响事件循环？"],
    "Redis": ["缓存和数据库发生不一致时，这段逻辑怎么恢复？", "这个 Key 的 TTL、幂等和并发边界应该怎样设计？"],
    "RAG": ["检索结果质量如何评估？为什么这里可能还需要 reranker？", "如果检索证据冲突或为空，生成链路如何降级？"],
    "LangGraph / Agent": ["为什么把这个步骤设计成独立 Agent/Node？", "失败、重试、审批和状态恢复的边界分别在哪里？"],
    "Pydantic": ["为什么这里需要结构化 Schema？只依赖 Prompt 有什么风险？"],
    "Testing": ["这段逻辑最应该补哪三类测试？哪些边界不能只靠单元测试？"],
    "Security": ["这段代码的信任边界在哪里？输入、权限和审计分别如何处理？"],
    "LLM Serving": ["模型服务超时、限流或输出不合法时，这里怎么处理？"],
}


def normalize_repo(provider: str, repo: str) -> tuple[str, str]:
    provider = provider.lower().strip()
    if provider not in {"github", "gitee"}:
        raise ValueError("provider must be github or gitee")
    raw = repo.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
            raise ValueError("Only credential-free HTTPS GitHub/Gitee URLs are allowed")
        url = raw[:-4] if raw.endswith(".git") else raw.rstrip("/")
        name = "/".join([x for x in parsed.path.strip("/").removesuffix(".git").split("/") if x][:2])
    else:
        parts = [x for x in raw.strip("/").removesuffix(".git").split("/") if x]
        if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) for x in parts):
            raise ValueError("repo must be owner/repository or a GitHub/Gitee HTTPS URL")
        host = "github.com" if provider == "github" else "gitee.com"
        name = f"{parts[0]}/{parts[1]}"
        url = f"https://{host}/{name}"
    expected_host = "github.com" if provider == "github" else "gitee.com"
    if urlparse(url).hostname not in {expected_host, f"www.{expected_host}"}:
        raise ValueError(f"provider={provider} does not match URL host")
    return url, name


def _symbols_for_python(content: str) -> list[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            symbols.append(f"async def {node.name}")
        elif isinstance(node, ast.FunctionDef):
            symbols.append(f"def {node.name}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}")
    return symbols[:30]


def analyze_code(path: str, content: str) -> dict:
    low = f"{path}\n{content}".lower()
    knowledge = [topic for topic, needles in KNOWLEDGE_RULES.items() if any(n in low for n in needles)]
    ext = Path(path).suffix.lower()
    if ext == ".py":
        symbols = _symbols_for_python(content)
    else:
        raw = re.findall(r"(?:class|function|def|interface)\s+([A-Za-z_][A-Za-z0-9_]*)", content)
        symbols = raw[:30]
    questions: list[str] = []
    for topic in knowledge:
        questions.extend(QUESTION_BY_TOPIC.get(topic, []))
    if symbols and not questions:
        questions.append(f"请解释 `{symbols[0]}` 的职责、输入输出和失败边界。")
    return {"knowledge": knowledge[:12], "symbols": symbols, "questions": questions[:8]}


async def _cmd(*args: str, cwd: str | None = None, timeout: int = 45) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError("Repository sync timed out")
    if proc.returncode != 0:
        raise RuntimeError((stderr.decode("utf-8", "replace") or stdout.decode("utf-8", "replace"))[-1200:])
    return stdout.decode("utf-8", "replace").strip()


def redact_secrets(text: str, secrets: list[str]) -> str:
    """Strip credentials (provider tokens) from messages that may reach the
    client or the logs — git error output can echo the clone URL."""
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "***")
    return text


def _clone_url(provider: str, name: str, url: str, access_token: str) -> str:
    """Authenticated clone URL. GitHub user tokens authenticate as
    x-access-token, Gitee OAuth tokens as oauth2; without a token the
    credential-free public URL is used unchanged."""
    if not access_token:
        return f"{url}.git"
    userinfo = "x-access-token" if provider == "github" else "oauth2"
    host = "github.com" if provider == "github" else "gitee.com"
    return f"https://{userinfo}:{access_token}@{host}/{name}.git"


async def clone_and_scan(
    provider: str,
    repo: str,
    branch: str,
    max_files: int = 260,
    previous_commit: str = "",
    access_token: str = "",
) -> dict:
    url, name = normalize_repo(provider, repo)
    with tempfile.TemporaryDirectory(prefix="interviewos-repo-") as tmp:
        target = Path(tmp) / "repo"
        try:
            await _cmd(
                "git", "clone", "--depth", "40", "--single-branch", "--branch", branch,
                _clone_url(provider, name, url, access_token), str(target), timeout=50,
            )
        except RuntimeError as exc:
            raise RuntimeError(redact_secrets(str(exc), [access_token])) from exc
        commit = await _cmd("git", "rev-parse", "HEAD", cwd=str(target), timeout=5)
        message = await _cmd("git", "log", "-1", "--pretty=%s", cwd=str(target), timeout=5)

        files: list[dict] = []
        total_bytes = 0
        for path in sorted(target.rglob("*")):
            if len(files) >= max_files or total_bytes >= 2_500_000:
                break
            if not path.is_file() or path.is_symlink():
                continue
            rel_parts = path.relative_to(target).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            ext = path.suffix.lower()
            if ext not in TEXT_EXTS and path.name not in {"Dockerfile", "docker-compose.yml", "compose.yml"}:
                continue
            size = path.stat().st_size
            if size > 120_000:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            total_bytes += len(content.encode("utf-8"))
            rel = path.relative_to(target).as_posix()
            analysis = analyze_code(rel, content)
            files.append({
                "path": rel,
                "language": LANGUAGE.get(ext, "Text"),
                "size": size,
                "content": content,
                "symbols": json.dumps(analysis["symbols"], ensure_ascii=False),
                "knowledge": json.dumps(analysis["knowledge"], ensure_ascii=False),
                "questions": json.dumps(analysis["questions"], ensure_ascii=False),
            })

        topics: dict[str, int] = {}
        languages: dict[str, int] = {}
        for item in files:
            languages[item["language"]] = languages.get(item["language"], 0) + 1
            for topic in json.loads(item["knowledge"]):
                topics[topic] = topics.get(topic, 0) + 1
        diff_summary = {
            "available": False,
            "changed": False,
            "from_commit": previous_commit[:12] if previous_commit else "",
            "to_commit": commit[:12],
            "shortstat": "",
            "files": [],
            "questions": [],
            "reason": "First sync establishes the baseline." if not previous_commit else "",
        }
        if previous_commit and previous_commit != commit:
            try:
                await _cmd("git", "cat-file", "-e", f"{previous_commit}^{{commit}}", cwd=str(target), timeout=5)
                name_status = await _cmd("git", "diff", "--name-status", previous_commit, commit, cwd=str(target), timeout=8)
                shortstat = await _cmd("git", "diff", "--shortstat", previous_commit, commit, cwd=str(target), timeout=8)
                changed_files = []
                for line in name_status.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        changed_files.append({"status": parts[0], "path": parts[-1]})
                file_lookup = {item["path"]: item for item in files}
                generated: list[str] = []
                for changed in changed_files[:30]:
                    current = file_lookup.get(changed["path"])
                    if current:
                        generated.extend(json.loads(current["questions"] or "[]")[:2])
                    elif changed["status"].startswith("D"):
                        generated.append(f"为什么删除 `{changed['path']}`？这个变化影响了哪条业务或依赖链路？")
                deduped = list(dict.fromkeys(generated))[:12]
                diff_summary = {
                    "available": True,
                    "changed": True,
                    "from_commit": previous_commit[:12],
                    "to_commit": commit[:12],
                    "shortstat": shortstat,
                    "files": changed_files[:30],
                    "questions": deduped,
                    "reason": "",
                }
            except RuntimeError:
                diff_summary["reason"] = "Previous commit is outside the shallow history; sync again after newer commits to enable local diff analysis."
        elif previous_commit == commit and previous_commit:
            diff_summary.update({"available": True, "changed": False, "reason": "Repository is already at the same commit."})

        summary = {
            "languages": sorted(languages.items(), key=lambda x: x[1], reverse=True)[:8],
            "topics": sorted(topics.items(), key=lambda x: x[1], reverse=True)[:10],
            "commit_message": message,
            "diff": diff_summary,
        }
        return {"url": url, "name": name, "branch": branch, "commit": commit, "files": files, "summary": summary}
