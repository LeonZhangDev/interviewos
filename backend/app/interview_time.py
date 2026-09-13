"""v0.9 interview time controller.

Compares actual elapsed time per script module (recorded when the candidate
enters a module, so thinking time counts) against the plan budget, and
produces an advisory telling the interviewer when to switch modules or wrap
up. Pure functions only — no DB access — so it is unit-testable and reused by
both the live time-status endpoint and the report.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

# Tolerance before a module is flagged as over budget (minutes).
OVER_BUDGET_GRACE = 1.5
# Remaining plan budget under which the wrap-up advisory fires (minutes).
WRAP_RESERVE = 6.0


def parse_module_starts(raw: str | None) -> dict[int, datetime]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    parsed: dict[int, datetime] = {}
    if not isinstance(data, dict):
        return parsed
    for key, value in data.items():
        try:
            parsed[int(key)] = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            continue
    return parsed


def serialize_module_starts(starts: dict[int, datetime]) -> str:
    return json.dumps({str(k): v.isoformat() for k, v in sorted(starts.items())})


def compute_time_status(
    script: list[dict[str, Any]],
    module_starts: dict[int, datetime],
    now: datetime,
    plan_minutes: int,
) -> dict[str, Any]:
    current_index = max(module_starts) if module_starts else None
    modules: list[dict[str, Any]] = []
    for index, item in enumerate(script):
        planned = int(item.get("minutes", 0) or 0)
        start = module_starts.get(index)
        if start is None:
            modules.append({
                "index": index,
                "type": item.get("type", ""),
                "planned_minutes": planned,
                "elapsed_minutes": 0.0,
                "status": "pending",
                "over_budget": False,
            })
            continue
        later_starts = [s for j, s in module_starts.items() if j > index]
        is_active = index == current_index
        end = min(later_starts) if later_starts else now
        elapsed = round(max(0.0, (end - start).total_seconds() / 60), 1)
        modules.append({
            "index": index,
            "type": item.get("type", ""),
            "planned_minutes": planned,
            "elapsed_minutes": elapsed,
            "status": "active" if is_active else "done",
            "over_budget": elapsed > planned + OVER_BUDGET_GRACE,
        })
    elapsed_total = round(sum(m["elapsed_minutes"] for m in modules), 1)
    return {
        "plan_minutes": plan_minutes,
        "elapsed_minutes": elapsed_total,
        "current_module": current_index,
        "modules": modules,
        "advisory": _advisory(modules, elapsed_total, plan_minutes, current_index),
    }


def _advisory(
    modules: list[dict[str, Any]],
    elapsed_total: float,
    plan_minutes: int,
    current_index: int | None,
) -> str:
    active = next((m for m in modules if m["index"] == current_index), None)
    if active and active["status"] == "active" and active["over_budget"]:
        return (
            f"当前模块「{active['type']}」已用 {active['elapsed_minutes']} 分钟"
            f"（预算 {active['planned_minutes']} 分钟），建议切换到下一模块或收尾。"
        )
    remaining = round(plan_minutes - elapsed_total, 1)
    if remaining <= WRAP_RESERVE:
        pending_wrap = next((m for m in modules if m.get("type") == "wrap" and m["status"] == "pending"), None)
        if pending_wrap:
            return f"计划时间剩约 {max(0, remaining)} 分钟，建议现在进入收尾模块。"
        return f"计划时间剩约 {max(0, remaining)} 分钟，建议尽快收尾。"
    return ""
