"""Unified search: cross-entity hits, per-group limits, and tenant isolation
between shared content and each user's private records."""
from __future__ import annotations

from tests.conftest import db_insert

GROUP_TYPES = {"question", "knowledge_node", "repo_file", "answer_version", "interview_turn"}


def _search(client, headers, q: str):
    response = client.get("/api/search", params={"q": q}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _groups(data: dict) -> dict[str, list[dict]]:
    return {group["type"]: group["items"] for group in data["groups"]}


def test_search_requires_auth_and_min_length(client, make_user):
    user = make_user()
    assert client.get("/api/search", params={"q": "gil"}).status_code == 401
    assert client.get("/api/search", params={"q": "g"}, headers=user["headers"]).status_code == 422
    assert client.get("/api/search", params={"q": "  "}, headers=user["headers"]).status_code == 422


def test_search_hits_shared_entities(client, make_user):
    data = _search(client, make_user()["headers"], "GIL")
    assert data["query"] == "GIL"
    assert {group["type"] for group in data["groups"]} == GROUP_TYPES
    assert data["total"] == sum(len(group["items"]) for group in data["groups"])

    items = _groups(data)
    assert any("GIL" in item["title"] for item in items["question"])
    assert any(item["id"] == "gil" for item in items["knowledge_node"])
    # shared groups are visible to every user, private groups start empty
    assert items["repo_file"] == []
    assert items["answer_version"] == []
    assert items["interview_turn"] == []


def test_search_finds_own_answers_repo_files_and_turns(client, make_user):
    alice = make_user("alice")
    questions = client.get("/api/questions", headers=alice["headers"]).json()
    gil_question = next(q for q in questions if q["slug"] == "python-gil")

    client.post(
        f"/api/questions/{gil_question['id']}/answers",
        json={"content": "xenon-marker GIL 限制线程并行，I/O 期间会释放执行权。"},
        headers=alice["headers"],
    )
    session_id = client.post("/api/interviews", json={}, headers=alice["headers"]).json()["id"]
    client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "聊聊 xenon-marker 分布式锁的误删问题", "answer": "用唯一 token 比较后再删除。"},
        headers=alice["headers"],
    )
    repo_id = db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', 'xenon-repo', 'https://github.com/alice/xenon', "
        "'main', 'abc', 1, '{}', 0, datetime('now'))",
        (alice["user"]["id"],),
    )
    db_insert(
        "INSERT INTO repo_files (repository_id, path, language, size, content, symbols, knowledge, questions) "
        "VALUES (?, 'app/xenon_marker.py', 'Python', 10, 'pass', '[\"xenon_marker\"]', '[]', '[]')",
        (repo_id,),
    )

    items = _groups(_search(client, alice["headers"], "xenon-marker"))
    assert [item["question_id"] for item in items["answer_version"]] == [gil_question["id"]]
    assert [item["session_id"] for item in items["interview_turn"]] == [session_id]
    assert [item["repo_id"] for item in items["repo_file"]] == [repo_id]
    assert any(item["title"].endswith("xenon_marker.py") for item in items["repo_file"])


def test_search_private_results_isolated(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    questions = client.get("/api/questions", headers=alice["headers"]).json()
    question_id = questions[0]["id"]
    client.post(
        f"/api/questions/{question_id}/answers",
        json={"content": "secret-marker 我的私有回答。"},
        headers=alice["headers"],
    )
    session_id = client.post("/api/interviews", json={}, headers=alice["headers"]).json()["id"]
    client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "secret-marker 私有面试问题", "answer": "私有回答。"},
        headers=alice["headers"],
    )
    repo_id = db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', 'secret-repo', 'https://github.com/alice/secret', "
        "'main', 'abc', 1, '{}', 0, datetime('now'))",
        (alice["user"]["id"],),
    )
    db_insert(
        "INSERT INTO repo_files (repository_id, path, language, size, content, symbols, knowledge, questions) "
        "VALUES (?, 'app/secret_marker.py', 'Python', 10, 'pass', '[]', '[]', '[]')",
        (repo_id,),
    )

    alice_items = _groups(_search(client, alice["headers"], "secret-marker"))
    assert len(alice_items["answer_version"]) == 1
    assert len(alice_items["interview_turn"]) == 1
    assert len(alice_items["repo_file"]) == 1

    bob_items = _groups(_search(client, bob["headers"], "secret-marker"))
    assert bob_items["answer_version"] == []
    assert bob_items["interview_turn"] == []
    assert bob_items["repo_file"] == []


def test_search_empty_result_and_group_limit(client, make_user):
    user = make_user()
    data = _search(client, user["headers"], "zzz-no-such-term-xyz")
    assert data["total"] == 0
    assert all(group["items"] == [] for group in data["groups"])

    # "e" is a single char (422) but "e我" style queries are legal; shared
    # question titles contain "什么" everywhere, so per_group caps the list.
    capped = _search(client, user["headers"], "什么")
    items = _groups(capped)
    assert 0 < len(items["question"]) <= 5
    capped_20 = client.get("/api/search", params={"q": "什么", "per_group": 20}, headers=user["headers"]).json()
    assert len(capped_20["groups"][0]["items"]) <= 20
