"""Question CMS: CRUD lifecycle with archive/restore, title-similarity
duplicate detection with force override, bulk tagging, and import preview
(dry-run) before the confirmed import writes."""
from __future__ import annotations


def _create(client, headers, force=False, **overrides):
    payload = {
        "category": "CMS",
        "title": "什么是可靠的多租户数据隔离设计？",
        "answer": "行级 ownership + 查询作用域 + 迁移回填，配合唯一约束与越权 404。",
        "code": "",
        "followups": "如何审计跨租户访问？",
        "difficulty": 3,
        "project_link": "InterviewOS",
        "tags": "backend|security",
    }
    payload.update(overrides)
    params = {"force": "true"} if force else None
    return client.post("/api/questions", json=payload, params=params, headers=headers)


def test_question_cms_requires_auth(client):
    assert client.post("/api/questions", json={"category": "x", "title": "t", "answer": "a"}).status_code == 401
    assert client.get("/api/questions/duplicates?title=x").status_code == 401
    assert client.post("/api/questions/1/archive").status_code == 401
    assert client.post("/api/questions/bulk-tag", json={"ids": [1], "tags": ["x"]}).status_code == 401


def test_crud_lifecycle_archive_and_restore(client, make_user):
    headers = make_user("cms_owner")["headers"]

    created = _create(client, headers)
    assert created.status_code == 201
    question = created.json()
    assert question["archived"] == 0
    assert question["tags"] == "backend|security"
    qid = question["id"]

    edited = client.patch(f"/api/questions/{qid}", json={"difficulty": 5, "title": "什么是可靠的多租户数据隔离设计（进阶）？"}, headers=headers)
    assert edited.status_code == 200
    assert edited.json()["difficulty"] == 5
    assert edited.json()["title"].endswith("（进阶）？")
    assert edited.json()["updated_at"] is not None

    archived = client.post(f"/api/questions/{qid}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["archived"] == 1

    active_ids = [q["id"] for q in client.get("/api/questions", headers=headers).json()]
    assert qid not in active_ids
    archived_ids = [q["id"] for q in client.get("/api/questions?archived=true", headers=headers).json()]
    assert qid in archived_ids

    search = client.get("/api/search?q=多租户数据隔离", headers=headers).json()
    question_hits = [i["id"] for g in search["groups"] if g["type"] == "question" for i in g["items"]]
    assert qid not in question_hits

    script = client.post("/api/interviews", json={"focus": ["CMS"], "duration": 15}, headers=headers)
    assert script.status_code == 200
    asked_ids = [step["question_id"] for step in script.json()["script"] if step.get("question_id")]
    assert qid not in asked_ids

    restored = client.post(f"/api/questions/{qid}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["archived"] == 0
    active_ids = [q["id"] for q in client.get("/api/questions", headers=headers).json()]
    assert qid in active_ids


def test_duplicate_detection_blocks_then_forces(client, make_user):  
    headers = make_user("cms_dup")["headers"]

    first = _create(client, headers, title="解释一下 Redis 持久化的 RDB 与 AOF 机制")
    assert first.status_code == 201

    similar = _create(client, headers, title="解释一下 Redis 持久化的 RDB 与 AOF 机制！")
    assert similar.status_code == 409
    detail = similar.json()["detail"]
    assert detail["duplicates"][0]["id"] == first.json()["id"]
    assert detail["duplicates"][0]["similarity"] >= 0.9

    forced = _create(client, headers, force=True, title="解释一下 Redis 持久化的 RDB 与 AOF 机制！")
    assert forced.status_code == 201
    assert forced.json()["id"] != first.json()["id"]

    found = client.get("/api/questions/duplicates?title=Redis 持久化 RDB AOF 机制", headers=headers).json()["duplicates"]
    assert {d["id"] for d in found} >= {first.json()["id"], forced.json()["id"]}

    unrelated = _create(client, headers, title="TCP 三次握手为什么不是两次？")
    assert unrelated.status_code == 201

    renamed = client.patch(f"/api/questions/{unrelated.json()['id']}", json={"title": "解释一下 Redis 持久化的 RDB 与 AOF 机制"}, headers=headers)
    assert renamed.status_code == 409


def test_bulk_tag_set_append_remove(client, make_user):  
    headers = make_user("cms_tags")["headers"]
    a = _create(client, headers, title="批量标签测试题 A", tags="").json()
    b = _create(client, headers, title="批量标签测试题 B", tags="old").json()

    assert client.post("/api/questions/bulk-tag", json={"ids": [a["id"], b["id"]], "mode": "append", "tags": ["redis", "cache"]}, headers=headers).json()["updated"] == 2
    assert client.get(f"/api/questions/{a['id']}", headers=headers).json()["tags"] == "redis|cache"
    assert client.get(f"/api/questions/{b['id']}", headers=headers).json()["tags"] == "old|redis|cache"

    assert client.post("/api/questions/bulk-tag", json={"ids": [a["id"]], "mode": "set", "tags": ["core"]}, headers=headers).json()["updated"] == 1
    assert client.get(f"/api/questions/{a['id']}", headers=headers).json()["tags"] == "core"

    assert client.post("/api/questions/bulk-tag", json={"ids": [b["id"]], "mode": "remove", "tags": ["redis"]}, headers=headers).json()["updated"] == 1
    assert client.get(f"/api/questions/{b['id']}", headers=headers).json()["tags"] == "old|cache"


def test_import_preview_does_not_write_until_confirmed(client, make_user):  
    headers = make_user("cms_import")["headers"]
    before = len(client.get("/api/questions", headers=headers).json())

    payload = {
        "format": "json",
        "content": '[{"category": "Agent", "title": "Agent 为什么需要记忆模块？", "answer": "跨步骤保存上下文。"},'
                   '{"category": "Agent", "title": "缺失答案的行", "answer": ""}]',
    }
    preview = client.post("/api/questions/import/preview", json=payload, headers=headers)
    assert preview.status_code == 200
    body = preview.json()
    assert body["total"] == 2
    assert body["to_create"] == 1
    assert body["to_skip"] == 1
    assert body["rows"][0]["status"] == "create"
    assert body["rows"][1]["status"] == "error"
    assert "title/answer required" in body["rows"][1]["problems"]

    assert len(client.get("/api/questions", headers=headers).json()) == before

    confirmed = client.post("/api/questions/import", json=payload, headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["created"] == 1
    assert confirmed.json()["skipped"] == 1

    after = client.get("/api/questions", headers=headers).json()
    assert len(after) == before + 1
    imported = next(q for q in after if q["title"] == "Agent 为什么需要记忆模块？")
    assert imported["updated_at"] is not None

    again = client.post("/api/questions/import/preview", json=payload, headers=headers).json()
    assert again["to_create"] == 0
    assert "duplicate slug" in again["rows"][0]["problems"]
