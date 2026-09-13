from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


@dataclass
class Symbol:
    id: str
    file: str
    name: str
    kind: str
    line: int
    calls: list[str]
    imports: list[str]


def _safe_json(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def parse_python_file(path: str, content: str) -> list[Symbol]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    file_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            file_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                file_imports.append(node.module)

    symbols: list[Symbol] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                fn = child.func
                if isinstance(fn, ast.Name):
                    calls.append(fn.id)
                elif isinstance(fn, ast.Attribute):
                    calls.append(fn.attr)
        kind = "class" if isinstance(node, ast.ClassDef) else "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
        symbols.append(Symbol(
            id=f"{path}:{node.name}:{getattr(node, 'lineno', 0)}",
            file=path,
            name=node.name,
            kind=kind,
            line=getattr(node, "lineno", 0),
            calls=sorted(set(calls))[:30],
            imports=sorted(set(file_imports))[:30],
        ))
    return symbols


def build_architecture(repo_files: Iterable[object], repo_name: str) -> dict:
    files = list(repo_files)
    nodes: list[dict] = []
    edges: list[dict] = []
    symbol_index: dict[str, list[Symbol]] = defaultdict(list)
    symbols: list[Symbol] = []
    topics = Counter()

    for file in files:
        path = getattr(file, "path", "")
        content = getattr(file, "content", "") or ""
        knowledge = _safe_json(getattr(file, "knowledge", "[]"))
        topics.update(knowledge)
        if path.endswith(".py"):
            parsed = parse_python_file(path, content)
            symbols.extend(parsed)
            for symbol in parsed:
                symbol_index[symbol.name].append(symbol)

    # Prefer architectural files; keep graph readable.
    ranked_files = sorted(
        files,
        key=lambda f: (
            -sum(token in getattr(f, "path", "").lower() for token in ("main", "router", "service", "agent", "rag", "repo", "db", "model", "client", "worker")),
            getattr(f, "path", ""),
        ),
    )[:22]
    file_ids = {getattr(f, "path", ""): f"file-{i}" for i, f in enumerate(ranked_files)}

    nodes.append({"id": "repo", "label": repo_name, "kind": "repository", "x": 30, "y": 40})
    for i, file in enumerate(ranked_files):
        path = getattr(file, "path", "")
        label = PurePosixPath(path).name
        x = 250 + (i % 4) * 230
        y = 30 + (i // 4) * 115
        nodes.append({"id": file_ids[path], "label": label, "subtitle": path, "kind": "file", "x": x, "y": y})
        if i < 6:
            edges.append({"id": f"repo-{i}", "source": "repo", "target": file_ids[path], "label": "contains"})

    # File-to-file dependency edges from Python imports.
    path_by_module: dict[str, str] = {}
    for path in file_ids:
        if path.endswith(".py"):
            module = path[:-3].replace("/", ".")
            path_by_module[module] = path
            path_by_module[PurePosixPath(path).stem] = path

    seen_edges: set[tuple[str, str]] = set()
    for symbol in symbols:
        source_path = symbol.file
        if source_path not in file_ids:
            continue
        for imp in symbol.imports:
            target_path = next((path for mod, path in path_by_module.items() if imp == mod or imp.endswith(f".{mod}") or mod.endswith(f".{imp}")), None)
            if target_path and target_path != source_path and target_path in file_ids:
                pair = (source_path, target_path)
                if pair not in seen_edges:
                    seen_edges.add(pair)
                    edges.append({"id": f"dep-{len(edges)}", "source": file_ids[source_path], "target": file_ids[target_path], "label": "imports"})

    questions: list[str] = []
    for symbol in symbols[:40]:
        if symbol.kind == "async_function":
            questions.append(f"`{symbol.name}` 为什么需要 async？它真正等待的 I/O 在哪里？")
        if any(call in {"commit", "rollback", "flush", "execute"} for call in symbol.calls):
            questions.append(f"`{symbol.name}` 的事务边界在哪里？失败时如何保证一致性？")
        if any(call in {"search", "retrieve", "rerank", "embed"} for call in symbol.calls):
            questions.append(f"`{symbol.name}` 的检索质量如何评估？召回不足时如何定位问题？")
    questions.extend([
        "为什么选择当前模块边界，而不是把逻辑都放在 Router 或 Agent Node 中？",
        "如果核心依赖不可用，这个架构的降级路径是什么？",
        "哪一个组件最可能成为性能瓶颈？你会如何观测和扩容？",
    ])
    questions = list(dict.fromkeys(questions))[:16]

    mermaid_lines = ["flowchart LR", f'  repo["{repo_name}"]']
    for node in nodes[1:]:
        mermaid_lines.append(f'  {node["id"].replace("-", "_")}["{node["label"]}"]')
    for edge in edges[:35]:
        source = edge["source"].replace("-", "_")
        target = edge["target"].replace("-", "_")
        mermaid_lines.append(f"  {source} -->|{edge['label']}| {target}")

    return {
        "nodes": nodes,
        "edges": edges[:40],
        "symbols": [s.__dict__ for s in symbols[:120]],
        "topics": topics.most_common(12),
        "questions": questions,
        "mermaid": "\n".join(mermaid_lines),
    }
