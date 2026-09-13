"""Tenant isolation: user A must never read or mutate user B's private
workbench data. Shared seed data (questions, coding challenges) stays visible
to everyone.
"""
from __future__ import annotations

from tests.conftest import db_insert, db_scalar


def _first_question_id(client, headers) -> int:
    questions = client.get("/api/questions", headers=headers)
    assert questions.status_code == 200
    return questions.json()[0]["id"]


def test_answer_versions_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    question_id = _first_question_id(client, alice["headers"])

    saved = client.post(
        f"/api/questions/{question_id}/answers",
        json={"content": "GIL 限制 CPU 密集线程并行，但 I/O 线程仍可让出执行权。"},
        headers=alice["headers"],
    )
    assert saved.status_code == 200
    assert saved.json()["score"] >= 0

    alice_answers = client.get(f"/api/questions/{question_id}/answers", headers=alice["headers"])
    bob_answers = client.get(f"/api/questions/{question_id}/answers", headers=bob["headers"])
    assert len(alice_answers.json()) == 1
    assert bob_answers.json() == []


def test_dashboard_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    question_id = _first_question_id(client, alice["headers"])
    client.post(
        f"/api/questions/{question_id}/answers",
        json={"content": "asyncio 单线程事件循环，await 处可能交错。"},
        headers=alice["headers"],
    )

    alice_dashboard = client.get("/api/dashboard", headers=alice["headers"]).json()
    bob_dashboard = client.get("/api/dashboard", headers=bob["headers"]).json()
    assert alice_dashboard["question_answered"] == 1
    assert alice_dashboard["streak"] >= 1
    assert bob_dashboard["question_answered"] == 0
    assert bob_dashboard["streak"] == 0


def test_interview_sessions_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    created = client.post("/api/interviews", json={}, headers=alice["headers"])
    assert created.status_code == 200
    session_id = created.json()["id"]

    turn = client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "介绍 FastAPI Depends 的作用", "answer": "依赖注入，处理横切逻辑。"},
        headers=alice["headers"],
    )
    assert turn.status_code == 200
    assert turn.json()["mode"] == "offline"

    assert client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "hi", "answer": "hi"},
        headers=bob["headers"],
    ).status_code == 404
    assert client.get(f"/api/interviews/{session_id}/turns", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/interviews/{session_id}/report", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/interviews/{session_id}/recordings", headers=bob["headers"]).status_code == 404

    bob_latest = client.get("/api/reports/latest", headers=bob["headers"]).json()
    assert bob_latest["session_id"] is None
    assert client.get("/api/reports/history", headers=bob["headers"]).json() == []

    alice_history = client.get("/api/reports/history", headers=alice["headers"]).json()
    assert [row["session_id"] for row in alice_history] == [session_id]


def test_report_content_isolated_between_users(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    session_id = client.post("/api/interviews", json={}, headers=alice["headers"]).json()["id"]
    client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "什么是幂等性", "answer": "同一操作执行多次结果相同。"},
        headers=alice["headers"],
    )

    report = client.get(f"/api/interviews/{session_id}/report", headers=alice["headers"])
    assert report.status_code == 200
    assert report.json()["turns"] == 1
    assert report.json()["overall_score"] > 0

    assert client.get(f"/api/interviews/{session_id}/report", headers=bob["headers"]).status_code == 404

    stored_owner = db_scalar("SELECT user_id FROM interview_reports WHERE session_id = ?", (session_id,))
    assert stored_owner == alice["user"]["id"]


def test_coding_wrongbook_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    challenges = client.get("/api/coding/challenges", headers=alice["headers"]).json()
    challenge_id = challenges[0]["id"]

    db_insert(
        "INSERT INTO coding_wrongbook (challenge_id, user_id, attempts, last_error, last_code, resolved, "
        "last_attempt_at) VALUES (?, ?, 2, 'timeout', 'code', 0, datetime('now'))",
        (challenge_id, alice["user"]["id"]),
    )

    alice_book = client.get("/api/coding/wrongbook", headers=alice["headers"]).json()
    bob_book = client.get("/api/coding/wrongbook", headers=bob["headers"]).json()
    assert [row["challenge_id"] for row in alice_book] == [challenge_id]
    assert bob_book == []


def test_coding_solved_flags_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    challenge_id = client.get("/api/coding/challenges", headers=alice["headers"]).json()[0]["id"]

    db_insert(
        "INSERT INTO coding_submissions (challenge_id, user_id, code, passed, public_passed, public_total, "
        "hidden_passed, hidden_total, time_complexity, space_complexity, time_match, space_match, mode, "
        "duration_ms, created_at) VALUES (?, ?, 'code', 1, 2, 2, 3, 3, 'O(n)', 'O(n)', 1, 1, 'practice', "
        "10.0, datetime('now'))",
        (challenge_id, alice["user"]["id"]),
    )

    alice_view = {c["id"]: c for c in client.get("/api/coding/challenges", headers=alice["headers"]).json()}
    bob_view = {c["id"]: c for c in client.get("/api/coding/challenges", headers=bob["headers"]).json()}
    assert alice_view[challenge_id]["solved"] is True
    assert bob_view[challenge_id]["solved"] is False
    assert bob_view[challenge_id]["wrongbook"] is False


def test_knowledge_graph_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', 'alice-secret-repo', 'https://github.com/alice/secret', "
        "'main', 'abc123', 3, '{}', 0, datetime('now'))",
        (alice["user"]["id"],),
    )

    alice_graph = client.get("/api/knowledge-graph", headers=alice["headers"]).json()
    bob_graph = client.get("/api/knowledge-graph", headers=bob["headers"]).json()

    alice_labels = {str(node.get("label", "")) for node in alice_graph["nodes"]}
    bob_labels = {str(node.get("label", "")) for node in bob_graph["nodes"]}
    assert "alice-secret-repo" in alice_labels
    assert "alice-secret-repo" not in bob_labels


def test_repositories_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    repo_id = db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', 'interviewos', 'https://github.com/alice/interviewos', "
        "'main', 'abc123', 1, '{}', 0, datetime('now'))",
        (alice["user"]["id"],),
    )
    file_id = db_insert(
        "INSERT INTO repo_files (repository_id, path, language, size, content, symbols, knowledge, questions) "
        "VALUES (?, 'app/main.py', 'Python', 100, 'print(1)', '[]', '[]', '[]')",
        (repo_id,),
    )

    assert client.get("/api/repos", headers=bob["headers"]).json() == []
    assert client.get("/api/repos", headers=alice["headers"]).json()[0]["id"] == repo_id

    assert client.get(f"/api/repos/{repo_id}/files", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/repos/{repo_id}/files/{file_id}", headers=bob["headers"]).status_code == 404
    assert client.get(f"/api/repos/{repo_id}/architecture", headers=bob["headers"]).status_code == 404
    assert client.patch(
        f"/api/repos/{repo_id}/visibility", json={"is_public": True}, headers=bob["headers"],
    ).status_code == 404
    assert client.post(
        f"/api/repos/{repo_id}/resume", json={"language": "zh", "style": "technical"}, headers=bob["headers"],
    ).status_code == 404

    assert client.get(f"/api/repos/{repo_id}/files", headers=alice["headers"]).status_code == 200


def test_recordings_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    session_id = client.post("/api/interviews", json={}, headers=alice["headers"]).json()["id"]

    upload = client.post(
        f"/api/interviews/{session_id}/recording",
        content=b"fake-webm-audio-bytes",
        headers={**alice["headers"], "Content-Type": "audio/webm"},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["id"]

    assert client.get(f"/api/interviews/{session_id}/recordings", headers=bob["headers"]).status_code == 404
    assert client.put(
        f"/api/interviews/{session_id}/recordings/{recording_id}/transcript",
        json={"transcript": "bob was here", "duration_ms": 1000},
        headers=bob["headers"],
    ).status_code == 404

    listed = client.get(f"/api/interviews/{session_id}/recordings", headers=alice["headers"]).json()
    assert len(listed) == 1
    assert listed[0]["transcript"] == ""

    saved = client.put(
        f"/api/interviews/{session_id}/recordings/{recording_id}/transcript",
        json={"transcript": "hello", "duration_ms": 1500},
        headers=alice["headers"],
    )
    assert saved.status_code == 200
    assert saved.json()["transcript"] == "hello"


def test_mastery_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    topic = "RAG"
    baseline = client.get("/api/learning/weakness", headers=bob["headers"]).json()
    bob_baseline = next(item["score"] for item in baseline if item["topic"] == topic)

    review = client.post(
        f"/api/learning/{topic}/review?grade=5",
        headers=alice["headers"],
    )
    assert review.status_code == 200

    alice_score = next(
        item["score"] for item in client.get("/api/learning/weakness", headers=alice["headers"]).json()
        if item["topic"] == topic
    )
    bob_score = next(
        item["score"] for item in client.get("/api/learning/weakness", headers=bob["headers"]).json()
        if item["topic"] == topic
    )
    assert alice_score > bob_score == bob_baseline


def test_import_history_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    payload = {
        "format": "json",
        "content": '[{"title": "什么是 WAL", "answer": "Write-ahead logging 先写日志再写数据页。", "category": "Database"}]',
    }
    imported = client.post("/api/questions/import", json=payload, headers=alice["headers"])
    assert imported.status_code == 200
    assert imported.json()["created"] == 1

    alice_history = client.get("/api/questions/import/history", headers=alice["headers"]).json()
    bob_history = client.get("/api/questions/import/history", headers=bob["headers"]).json()
    assert len(alice_history) == 1
    assert bob_history == []


def test_shared_question_bank_visible_to_all(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    alice_questions = client.get("/api/questions", headers=alice["headers"]).json()
    bob_questions = client.get("/api/questions", headers=bob["headers"]).json()
    assert alice_questions and [q["id"] for q in alice_questions] == [q["id"] for q in bob_questions]
