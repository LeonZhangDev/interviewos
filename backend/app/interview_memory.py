"""v0.9 interview memory.

Deterministic cross-turn analysis of a single interview session. Finds:

- contradictions: opposite stances on the same topic in different answers
- unanswered / evasion: explicit dodge phrases or extremely short answers
- avoided concepts: reference key points never mentioned across turns
- reused gaps: a concept the candidate failed to cover earlier but keeps
  using later

All detectors are pure functions over plain turn dicts so they work offline;
the LLM only enriches the final summary.
"""
from __future__ import annotations

import re
from typing import Any

from .ai import ask_json
from .scoring import extract_terms, score_answer

# (label, positive regex, negative regex) — mutually exclusive stances.
STANCE_PAIRS = [
    ("分布式锁过期时间", r"一定要设置过期|必须设置过期|一定要有过期", r"不需要设置过期|不用设置过期|无需设置过期"),
    ("阻塞行为", r"会阻塞|将阻塞|阻塞了", r"不会阻塞|不阻塞|非阻塞"),
    ("加锁", r"需要加锁|要加锁|应该加锁", r"不需要加锁|不用加锁|无需加锁"),
    ("线程模型", r"是单线程|只有一个线程", r"是多线程|有多个线程"),
]

AVOIDANCE_PHRASES = ["不知道", "不清楚", "没了解过", "没研究过", "没接触过", "跳过", "这块不熟", "记不清"]
SHORT_ANSWER_CHARS = 15
AVOIDED_CONCEPT_MIN_TURNS = 2

KIND_LABELS = {
    "contradiction": "前后矛盾",
    "evasion": "回避问题",
    "unanswered": "未正面回答",
    "avoided_concept": "反复回避的关键点",
    "reused_gap": "之前没答出但后面重复使用",
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？.!?\n]+", text or "") if s.strip()]


def detect_contradictions(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag a stance pair asserted positively in one turn and negatively in a
    different turn, when both sentences share at least one technical term —
    same-subject only, so intentional contrasts about different subjects stay
    unflagged."""
    findings: list[dict[str, Any]] = []
    for label, positive, negative in STANCE_PAIRS:
        positives: list[dict[str, Any]] = []
        negatives: list[dict[str, Any]] = []
        for turn in turns:
            for sentence in _sentences(turn.get("answer", "")):
                if re.search(negative, sentence):
                    negatives.append({"turn": turn["index"], "sentence": sentence})
                elif re.search(positive, sentence):
                    positives.append({"turn": turn["index"], "sentence": sentence})
        if not positives or not negatives:
            continue
        for hit_pos in positives:
            matched = next(
                (hit_neg for hit_neg in negatives
                 if hit_neg["turn"] != hit_pos["turn"]
                 and set(extract_terms(hit_pos["sentence"])) & set(extract_terms(hit_neg["sentence"]))),
                None,
            )
            if matched:
                findings.append({
                    "kind": "contradiction",
                    "turns": [hit_pos["turn"], matched["turn"]],
                    "detail": (
                        f"关于「{label}」的说法前后矛盾：第 {hit_pos['turn'] + 1} 轮说『{hit_pos['sentence'][:60]}』，"
                        f"第 {matched['turn'] + 1} 轮又说『{matched['sentence'][:60]}』。"
                    ),
                })
                break
    return findings


def detect_unanswered(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for turn in turns:
        answer = (turn.get("answer") or "").strip()
        if not answer:
            continue
        if any(phrase in answer for phrase in AVOIDANCE_PHRASES):
            findings.append({
                "kind": "evasion",
                "turns": [turn["index"]],
                "detail": f"第 {turn['index'] + 1} 轮疑似回避问题：「{answer[:40]}」。真实面试中面试官通常会换个角度再问一次。",
            })
        elif len(answer) < SHORT_ANSWER_CHARS:
            findings.append({
                "kind": "unanswered",
                "turns": [turn["index"]],
                "detail": f"第 {turn['index'] + 1} 轮回答只有 {len(answer)} 个字，问题没有被正面回答。",
            })
    return findings


def detect_avoided_concepts(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing_turns: dict[str, list[int]] = {}
    for turn in turns:
        if not turn.get("reference"):
            continue
        for term in score_answer(turn["reference"], turn["answer"])["missing_terms"]:
            missing_turns.setdefault(term, []).append(turn["index"])
    findings: list[dict[str, Any]] = []
    for term, indexes in missing_turns.items():
        if len(indexes) >= AVOIDED_CONCEPT_MIN_TURNS:
            turns_text = "、".join(f"第 {i + 1} 轮" for i in indexes)
            findings.append({
                "kind": "avoided_concept",
                "turns": indexes,
                "detail": f"「{term}」在 {turns_text}的参考要点里都出现过，但你的回答从未提及——这是一个被反复回避的关键点。",
            })
    return findings


def detect_reused_gaps(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    missing_since: dict[str, int] = {}
    for turn in turns:
        if turn.get("reference"):
            for term in score_answer(turn["reference"], turn["answer"])["missing_terms"]:
                missing_since.setdefault(term, turn["index"])
        answer_low = turn.get("answer", "").lower()
        for term, first_index in list(missing_since.items()):
            if turn["index"] > first_index and term in answer_low:
                findings.append({
                    "kind": "reused_gap",
                    "turns": [first_index, turn["index"]],
                    "detail": f"「{term}」在第 {first_index + 1} 轮没有答出，但第 {turn['index'] + 1} 轮又直接使用了它——面试官通常会当场追问它的原理。",
                })
                del missing_since[term]
    return findings


def analyze_session(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    findings.extend(detect_contradictions(turns))
    findings.extend(detect_unanswered(turns))
    findings.extend(detect_avoided_concepts(turns))
    findings.extend(detect_reused_gaps(turns))
    return findings


def build_memory_context(turns: list[dict[str, Any]], limit: int = 6) -> str:
    """Compact digest of findings from PRIOR turns, injected into the judge /
    follow-up prompts so the interviewer can call them out live."""
    findings = analyze_session(turns)
    if not findings:
        return ""
    lines = [f"- [{KIND_LABELS.get(f['kind'], f['kind'])}] {f['detail']}" for f in findings[:limit]]
    return "面试记忆（本轮面试之前回答中发现的问题，追问时可以点名）：\n" + "\n".join(lines)


async def summarize_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "没有发现明显的矛盾、回避或反复缺失的关键点。"
    kinds = "、".join(sorted({KIND_LABELS.get(f["kind"], f["kind"]) for f in findings}))
    summary = f"面试记忆共发现 {len(findings)} 项问题：{kinds}。建议在复盘时逐条对照原文。"
    llm = await ask_json(
        "你是面试复盘助手。基于确定性检测出的发现，输出 JSON：summary（不超过 120 字的中文总结，指出最值得复盘的两三个点）。不要输出额外文本。",
        "发现清单：\n" + "\n".join(f"- [{f['kind']}] {f['detail']}" for f in findings[:12]),
    )
    if llm and llm.get("summary"):
        summary = str(llm["summary"])[:500]
    return summary
