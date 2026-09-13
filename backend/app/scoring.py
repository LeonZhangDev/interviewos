from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

TECH_TERMS = [
    "gil", "cpython", "asyncio", "await", "coroutine", "task", "future", "lock", "semaphore",
    "fastapi", "depends", "middleware", "session", "asyncsession", "sqlalchemy", "transaction",
    "postgresql", "mysql", "index", "join", "n+1", "joinedload", "selectinload", "redis",
    "cache-aside", "cache aside", "ttl", "nx", "px", "rag", "embedding", "reranker", "bge-m3",
    "langgraph", "llamaindex", "agent", "tool calling", "tool schema", "mcp", "approval",
    "deterministic", "executor", "audit", "idempotent", "幂等", "审计", "审批", "确定性",
    "检索", "重排", "缓存", "事务", "索引", "并发", "竞态", "临界区", "依赖注入",
    "复杂度", "hashmap", "哈希", "sandbox", "沙箱", "docker", "timeout", "memory",
]

DEPTH_MARKERS = [
    "因为", "所以", "但是", "因此", "同时", "边界", "失败", "异常", "重试", "权衡", "风险",
    "tradeoff", "because", "failure", "retry", "boundary", "risk", "however", "instead",
]


def extract_terms(text: str) -> list[str]:
    low = text.lower()
    found = {term for term in TECH_TERMS if term in low}
    # Keep identifiers/acronyms as extra terms without trying to segment Chinese prose.
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_+.-]{2,}", text):
        if len(token) <= 32:
            found.add(token.lower())
    return sorted(found)


def score_answer(reference: str, answer: str) -> dict[str, Any]:
    answer = answer.strip()
    if not answer:
        return {"score": 0.0, "dimensions": {"coverage": 0, "structure": 0, "clarity": 0, "depth": 0}, "missing_terms": []}

    reference_terms = extract_terms(reference)
    answer_low = answer.lower()
    matched = [term for term in reference_terms if term in answer_low]
    missing = [term for term in reference_terms if term not in answer_low][:8]

    if reference_terms:
        coverage = 35 + 65 * len(matched) / len(reference_terms)
    else:
        similarity = SequenceMatcher(None, reference[:500], answer[:500]).ratio()
        coverage = 45 + similarity * 45

    sentence_count = len([x for x in re.split(r"[。！？.!?\n]+", answer) if x.strip()])
    has_structure_words = sum(1 for x in ["首先", "其次", "最后", "核心", "本质", "一是", "二是", "1.", "2."] if x in answer)
    structure = min(100, 48 + sentence_count * 7 + has_structure_words * 8)

    length = len(answer)
    if 90 <= length <= 650:
        clarity = 88
    elif 45 <= length < 90:
        clarity = 72
    elif length > 650:
        clarity = max(55, 90 - (length - 650) / 25)
    else:
        clarity = max(35, 45 + length / 4)

    depth_hits = sum(1 for marker in DEPTH_MARKERS if marker in answer_low)
    depth = min(100, 45 + depth_hits * 8 + min(len(matched), 5) * 4)

    total = coverage * 0.45 + structure * 0.15 + clarity * 0.15 + depth * 0.25
    total = round(max(20, min(98, total)), 1)
    return {
        "score": total,
        "dimensions": {
            "coverage": round(coverage),
            "structure": round(structure),
            "clarity": round(clarity),
            "depth": round(depth),
        },
        "matched_terms": matched[:10],
        "missing_terms": missing,
    }
