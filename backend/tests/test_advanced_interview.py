"""v0.9 advanced interview: interviewer personas, interview memory, and the
interview time controller. Runs fully offline (deterministic detectors and
fallback scoring), matching the rest of the suite."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.interview_memory import analyze_session, build_memory_context
from app.interview_time import compute_time_status
from app.personas import PERSONAS, build_time_plan


def _make_session(client, user, **payload) -> dict:
    created = client.post("/api/interviews", json={"duration": 30, **payload}, headers=user["headers"])
    assert created.status_code == 200, created.text
    return created.json()


def _submit_turn(client, user, session_id: int, prompt: str, answer: str, module_index: int | None = None) -> dict:
    response = client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": prompt, "answer": answer, "module_index": module_index},
        headers=user["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- personas


def test_all_personas_accepted_and_persisted(client, make_user):
    user = make_user("persona-owner")
    for persona_id in PERSONAS:
        created = _make_session(client, user, persona=persona_id)
        assert created["persona"] == persona_id


def test_unknown_persona_rejected(client, make_user):
    user = make_user("persona-hater")
    response = client.post("/api/interviews", json={"persona": "yandere"}, headers=user["headers"])
    assert response.status_code == 422


def test_personas_listing(client, make_user):
    user = make_user("persona-lister")
    listing = client.get("/api/interviews/personas", headers=user["headers"])
    assert listing.status_code == 200
    items = listing.json()
    assert {item["id"] for item in items} == set(PERSONAS)
    assert all(item["label"] and item["description"] and item["emphasis"] for item in items)


def test_script_follows_time_plan_budgets(client, make_user):
    user = make_user("plan-checker")
    for duration in (30, 45, 60):
        plan = build_time_plan(duration)
        created = _make_session(client, user, duration=duration)
        script = created["script"]
        assert script[0]["type"] == "intro"
        assert script[0]["minutes"] == plan["intro"]
        assert script[-1]["type"] == "wrap"
        assert script[-1]["minutes"] == plan["wrap"]
        questions = [item for item in script if item["type"] not in ("intro", "wrap")]
        assert 4 <= len(questions) <= plan["max_questions"]
        assert all(item["minutes"] == plan["per_question"] for item in questions)
        assert sum(item["minutes"] for item in script) <= duration


def test_persona_keeps_factual_scoring_standard(client, make_user):
    """Personas style the questioning and the judge emphasis, but the offline
    factual baseline must stay identical across personas for the same answer."""
    user = make_user("fact-checker")
    prompt = "解释 FastAPI 的 Depends 依赖注入与中间件的差异"
    answer = "Depends 用于声明依赖并做缓存，中间件处理请求生命周期，两者作用层面不同。"
    scores = {}
    for persona_id in ("normal", "friendly", "pressure"):
        session = _make_session(client, user, persona=persona_id)
        scores[persona_id] = _submit_turn(client, user, session["id"], prompt, answer)["score"]
    assert len(set(scores.values())) == 1


# ------------------------------------------------------------ memory


def test_memory_flags_cross_turn_contradiction(client, make_user):
    user = make_user("memory-contradiction")
    session = _make_session(client, user)
    _submit_turn(
        client, user, session["id"],
        "Redis 分布式锁需要设置过期时间吗？",
        "Redis 分布式锁一定要设置过期时间，否则进程崩溃后锁永远无法释放，会造成死锁。",
    )
    _submit_turn(
        client, user, session["id"],
        "那锁的续期怎么处理？",
        "Redis 锁不需要设置过期时间，靠看门狗线程不断续期就可以一直持有。",
    )
    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    kinds = [finding["kind"] for finding in report["memory"]["findings"]]
    assert "contradiction" in kinds
    assert report["memory"]["summary"]


def test_memory_ignores_same_turn_contrast(client, make_user):
    user = make_user("memory-contrast")
    session = _make_session(client, user)
    _submit_turn(
        client, user, session["id"],
        "await 会阻塞吗？",
        "网络 IO 会阻塞事件循环，但 await 不会阻塞线程，它只是让出控制权。这是一个关键区别。",
    )
    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    kinds = [finding["kind"] for finding in report["memory"]["findings"]]
    assert "contradiction" not in kinds


def test_memory_flags_evasion_and_unanswered(client, make_user):
    user = make_user("memory-evasion")
    session = _make_session(client, user)
    _submit_turn(client, user, session["id"], "讲讲 GIL", "这块没接触过，跳过吧。")
    _submit_turn(client, user, session["id"], "讲讲 asyncio 事件循环", "我忘了。")
    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    kinds = {finding["kind"] for finding in report["memory"]["findings"]}
    assert "evasion" in kinds
    assert "unanswered" in kinds


def test_memory_flags_repeatedly_avoided_concept(client, make_user):
    user = make_user("memory-avoid")
    session = _make_session(client, user)
    generic = "这个问题主要取决于解释器实现细节，我认为要结合具体场景看，不能一概而论。"
    _submit_turn(client, user, session["id"], "请解释 Python GIL 对多线程的影响", generic)
    _submit_turn(client, user, session["id"], "再说说 GIL 与 asyncio 的关系", generic)
    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    assert any(
        finding["kind"] == "avoided_concept" and "gil" in finding["detail"]
        for finding in report["memory"]["findings"]
    )


def test_memory_flags_reused_gap(client, make_user):
    user = make_user("memory-reuse")
    session = _make_session(client, user)
    _submit_turn(client, user, session["id"], "请解释 Python GIL 的作用", "这个问题我不展开，主要看版本和实现。")
    _submit_turn(client, user, session["id"], "讲讲你的多线程优化经验", "我会用 GIL 感知的方式做优化，把重计算放到多进程里。")
    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    assert any(finding["kind"] == "reused_gap" for finding in report["memory"]["findings"])


def test_live_turn_feedback_carries_memory(client, make_user):
    """While the interview is running (offline), the interviewer calls out a
    contradiction found in earlier answers."""
    user = make_user("memory-live")
    session = _make_session(client, user)
    _submit_turn(client, user, session["id"], "Redis 锁要设置过期时间吗？", "Redis 锁一定要设置过期时间，否则会死锁。")
    _submit_turn(client, user, session["id"], "续期怎么办？", "Redis 锁不需要设置过期时间，看门狗续期就行。")
    third = _submit_turn(client, user, session["id"], "总结一下你的方案", "我的方案是取两者的折中：设置合理的过期时间并配合自动续期。")
    assert "面试官记忆" in third["feedback"]


def test_build_memory_context_renders_findings():
    turns = [
        {"index": 0, "prompt": "q1", "answer": "Redis 锁一定要设置过期时间。"},
        {"index": 1, "prompt": "q2", "answer": "Redis 锁不需要设置过期时间，看门狗续期就行。"},
    ]
    context = build_memory_context(turns)
    assert "面试记忆" in context
    assert "前后矛盾" in context
    clean = "这个问题我会先讲结论再解释原因，覆盖主要概念、边界条件与失败场景，内容足够长。"
    assert build_memory_context([{"index": 0, "prompt": "q", "answer": clean}]) == ""


# ------------------------------------------------------ time controller


def test_module_start_and_time_status(client, make_user):
    user = make_user("time-basic")
    session = _make_session(client, user)
    script = session["script"]
    started = client.post(f"/api/interviews/{session['id']}/modules/0/start", headers=user["headers"])
    assert started.status_code == 200
    status = started.json()
    assert status["plan_minutes"] == 30
    assert len(status["modules"]) == len(script)
    assert status["modules"][0]["status"] == "active"
    assert all(module["status"] == "pending" for module in status["modules"][1:])

    _submit_turn(client, user, session["id"], "自我介绍", "我是后端工程师，主要负责 FastAPI 服务与 Agent 系统。", module_index=0)
    turns = client.get(f"/api/interviews/{session['id']}/turns", headers=user["headers"]).json()
    assert turns[0]["module_index"] == 0

    fetched = client.get(f"/api/interviews/{session['id']}/time-status", headers=user["headers"]).json()
    assert fetched["current_module"] == 0
    assert fetched["persona"] == "normal"


def test_module_start_rejects_unknown_module(client, make_user):
    user = make_user("time-bounds")
    session = _make_session(client, user)
    response = client.post(f"/api/interviews/{session['id']}/modules/999/start", headers=user["headers"])
    assert response.status_code == 404


def test_time_status_isolated_per_user(client, make_user):
    owner = make_user("time-owner")
    intruder = make_user("time-intruder")
    session = _make_session(client, owner)
    assert client.get(f"/api/interviews/{session['id']}/time-status", headers=intruder["headers"]).status_code == 404
    assert client.post(f"/api/interviews/{session['id']}/modules/0/start", headers=intruder["headers"]).status_code == 404


def test_report_persists_memory_and_time(client, make_user):
    from tests.conftest import db_scalar

    user = make_user("report-persist")
    session = _make_session(client, user)
    client.post(f"/api/interviews/{session['id']}/modules/0/start", headers=user["headers"])
    _submit_turn(client, user, session["id"], "GIL 是什么", "Redis 锁一定要设置过期时间，否则会死锁。")
    _submit_turn(client, user, session["id"], "再问锁的续期", "Redis 锁不需要设置过期时间，看门狗续期就行。", module_index=1)

    report = client.get(f"/api/interviews/{session['id']}/report", headers=user["headers"]).json()
    assert report["memory"]["findings"]
    assert report["time"]["modules"] and report["time"]["plan_minutes"] == 30

    memory_raw = db_scalar("SELECT memory_findings FROM interview_reports WHERE session_id = ?", (session["id"],))
    time_raw = db_scalar("SELECT time_execution FROM interview_reports WHERE session_id = ?", (session["id"],))
    assert memory_raw and "contradiction" in memory_raw
    assert time_raw and "modules" in time_raw


def test_compute_time_status_flags_over_budget_module():
    script = [
        {"type": "intro", "minutes": 2},
        {"type": "Python", "minutes": 5},
        {"type": "wrap", "minutes": 3},
    ]
    now = datetime(2026, 9, 9, 12, 0, 0)
    starts = {0: now - timedelta(minutes=12), 1: now - timedelta(minutes=8)}
    status = compute_time_status(script, starts, now, plan_minutes=30)
    assert status["modules"][0]["status"] == "done"
    assert status["modules"][0]["elapsed_minutes"] == 4.0
    assert status["modules"][0]["over_budget"] is True
    assert status["modules"][1]["status"] == "active"
    assert status["modules"][1]["elapsed_minutes"] == 8.0
    assert status["current_module"] == 1
    assert "建议切换" in status["advisory"]


def test_compute_time_status_advises_wrap_when_time_runs_out():
    script = [
        {"type": "intro", "minutes": 2},
        {"type": "Python", "minutes": 5},
        {"type": "wrap", "minutes": 3},
    ]
    now = datetime(2026, 9, 9, 12, 0, 0)
    starts = {0: now - timedelta(minutes=25), 1: now - timedelta(minutes=2)}
    status = compute_time_status(script, starts, now, plan_minutes=30)
    assert status["modules"][1]["over_budget"] is False
    assert "收尾" in status["advisory"]


def test_compute_time_status_empty_session():
    status = compute_time_status([], {}, datetime(2026, 9, 9, 12, 0, 0), plan_minutes=45)
    assert status["modules"] == []
    assert status["current_module"] is None
    assert status["advisory"] == ""
