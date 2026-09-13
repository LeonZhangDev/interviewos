"""Offline end-to-end workflows: without an LLM provider and without the
Runner service, the core learner loop must still work end to end.
"""
from __future__ import annotations

from tests.conftest import db_insert


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "1.0.0"


def test_llm_status_reports_offline(client, make_user):
    user = make_user("alice")
    response = client.get("/api/llm/status", headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["mode"] == "offline"


def test_question_list_and_detail(client, make_user):
    user = make_user("alice")
    questions = client.get("/api/questions", headers=user["headers"]).json()
    assert len(questions) >= 20

    python = client.get("/api/questions?category=Python", headers=user["headers"]).json()
    assert python and all(q["category"] == "Python" for q in python)

    search = client.get("/api/questions?q=GIL", headers=user["headers"]).json()
    assert any("GIL" in q["title"] for q in search)

    first = questions[0]["id"]
    detail = client.get(f"/api/questions/{first}", headers=user["headers"])
    assert detail.status_code == 200
    assert client.get("/api/questions/999999", headers=user["headers"]).status_code == 404


def test_save_answer_updates_mastery_and_versions(client, make_user):
    user = make_user("alice")
    question_id = client.get("/api/questions", headers=user["headers"]).json()[0]["id"]

    first = client.post(
        f"/api/questions/{question_id}/answers",
        json={"content": "短回答"},
        headers=user["headers"],
    )
    assert first.status_code == 200
    assert "mastery" in first.json()

    second = client.post(
        f"/api/questions/{question_id}/answers",
        json={"content": "更完整的回答，覆盖关键概念与边界。"},
        headers=user["headers"],
    )
    assert second.status_code == 200

    versions = client.get(f"/api/questions/{question_id}/answers", headers=user["headers"]).json()
    assert len(versions) == 2
    assert versions[0]["created_at"] >= versions[1]["created_at"]

    weakness = client.get("/api/learning/weakness", headers=user["headers"]).json()
    assert weakness, "bootstrap should seed an initial mastery map"


def test_review_updates_schedule(client, make_user):
    user = make_user("alice")
    before = client.get("/api/learning/weakness", headers=user["headers"]).json()
    target = before[0]["topic"]

    reviewed = client.post(f"/api/learning/{target}/review?grade=4", headers=user["headers"])
    assert reviewed.status_code == 200
    assert reviewed.json()["interval_days"] >= 2
    assert client.post(f"/api/learning/unknown-topic-x/review?grade=4", headers=user["headers"]).status_code == 404
    assert client.post(f"/api/learning/{target}/review?grade=9", headers=user["headers"]).status_code == 422


def test_full_interview_flow_with_sse_stream(client, make_user):
    user = make_user("alice")
    created = client.post("/api/interviews", json={"duration": 30}, headers=user["headers"])
    assert created.status_code == 200
    session = created.json()
    assert session["script"] and session["script"][0]["type"] == "intro"

    with client.stream(
        "POST",
        f"/api/interviews/{session['id']}/stream-turn",
        json={"interviewer_prompt": "介绍你最有代表性的项目", "answer": "InterviewOS：题库、Judge、AI 面试与间隔复习闭环。"},
        headers=user["headers"],
    ) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        text = "".join(part for part in stream.iter_text())
    assert "event: analysis" in text
    assert "event: followup_start" in text
    assert "event: done" in text

    turns = client.get(f"/api/interviews/{session['id']}/turns", headers=user["headers"]).json()
    assert len(turns) == 1
    assert turns[0]["score"] >= 0

    report = client.get(f"/api/reports/latest", headers=user["headers"]).json()
    assert report["session_id"] == session["id"]
    assert report["turns"] == 1


def test_code_explanation_offline(client, make_user):
    user = make_user("alice")
    response = client.post(
        "/api/code/explain",
        json={
            "source_title": "Code Lab",
            "code": "def add(a, b):\n    return a + b\n",
            "explanation": "一个简单的加法函数，接收两个参数返回其和。",
        },
        headers=user["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "offline"
    assert 0 <= body["score"] <= 100
    assert body["feedback"]

    from tests.conftest import db_scalar
    owner = db_scalar("SELECT user_id FROM code_explanation_attempts ORDER BY id DESC")
    assert owner == user["user"]["id"]


def test_resume_generation_offline(client, make_user):
    user = make_user("alice")
    repo_id = db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', 'demo-repo', 'https://github.com/alice/demo-repo', "
        "'main', 'abc123', 1, '{}', 0, datetime('now'))",
        (user["user"]["id"],),
    )
    db_insert(
        "INSERT INTO repo_files (repository_id, path, language, size, content, symbols, knowledge, questions) "
        "VALUES (?, 'service.py', 'Python', 120, 'async def handler():\\n    pass', "
        "'[]', '[\"async\", \"FastAPI\"]', '[]')",
        (repo_id,),
    )

    response = client.post(
        f"/api/repos/{repo_id}/resume",
        json={"language": "zh", "style": "technical"},
        headers=user["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "offline"
    assert "demo-repo" in body["text"]
    assert body["evidence"]["files"] == 1


def test_system_design_cases_and_evaluation(client, make_user):
    user = make_user("alice")
    cases = client.get("/api/system-design/cases", headers=user["headers"]).json()
    assert {case["id"] for case in cases} >= {"python-runner", "rag-service"}

    canvas = client.put(
        "/api/system-design/canvas",
        json={"case_id": "python-runner", "title": "My plan", "nodes": [{"id": "n1"}], "edges": []},
        headers=user["headers"],
    )
    assert canvas.status_code == 200
    loaded = client.get("/api/system-design/canvas/python-runner", headers=user["headers"]).json()
    assert loaded["title"] == "My plan"

    evaluated = client.post(
        "/api/system-design/python-runner/evaluate",
        json={"content": "API 网关、任务队列、隔离沙箱 Runner、结果存储、可观测与告警。"},
        headers=user["headers"],
    )
    assert evaluated.status_code == 200
    assert "score" in evaluated.json()


def test_projects_endpoint(client, make_user):
    user = make_user("alice")
    projects = client.get("/api/projects", headers=user["headers"]).json()
    assert {p["name"] for p in projects} >= {"MindTrip", "AtlasSplit", "InterviewOS"}
