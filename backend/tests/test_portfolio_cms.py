"""v1.0 P2 Portfolio CMS: profile/project CRUD, ordering, publishing and the
public-view privacy contract.

Privacy invariants covered here:
- every CMS route is user-scoped; foreign ids are indistinguishable from
  missing ones (404),
- unpublished portfolios keep serving the exact legacy static shape,
- the published view only contains explicitly configured fields plus projects
  the user marked visible,
- a project bound to a repository only reveals that repository when the
  repository itself is public (is_private / is_public stay decoupled),
- no private learning data (wrong book, mastery, answers, recordings) ever
  appears in the public payload.
"""
from __future__ import annotations

from tests.conftest import db_insert


def _insert_repo(user_id: int, name: str, is_public: int, is_private: int = 0) -> int:
    return db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, is_private, synced_at) VALUES (?, 'github', ?, ?, 'main', 'abc123def456', 2, '{}', ?, ?, datetime('now'))",
        (user_id, name, f"https://github.com/user/{name}", is_public, is_private),
    )


def _profile(client, headers):
    return client.get("/api/portfolio-cms/profile", headers=headers)


def _put_profile(client, headers, **overrides):
    payload = {
        "display_name": "Alice",
        "headline": "Backend / AI Engineer",
        "summary": "Building deterministic agent systems.",
        "skills": ["Python", "FastAPI"],
        "resume_url": "https://example.com/resume.pdf",
        "social_links": {"github": "https://github.com/alice", "blog": "https://alice.dev"},
        "is_published": False,
    }
    payload.update(overrides)
    return client.put("/api/portfolio-cms/profile", json=payload, headers=headers)


def _post_project(client, headers, **overrides):
    payload = {
        "title": "InterviewOS",
        "subtitle": "AI Engineer Interview Workbench",
        "description": "闭环面试工作台。",
        "architecture": "Core -> Gameplay -> Infrastructure.",
        "decisions": "用户代码只进独立 Runner。",
        "tech_tags": ["FastAPI", "React"],
        "link": "https://example.com/demo",
        "repository_id": None,
        "is_visible": True,
    }
    payload.update(overrides)
    return client.post("/api/portfolio-cms/projects", json=payload, headers=headers)


# --- profile ---------------------------------------------------------------


def test_profile_auto_created_with_defaults(client, make_user):
    alice = make_user("alice")
    response = _profile(client, alice["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["is_published"] is False
    assert body["skills"] == []
    assert body["social_links"] == {}
    assert body["display_name"] == "Alice"  # falls back to user display_name


def test_profile_update_roundtrip_and_publish_toggle(client, make_user):
    alice = make_user("alice")
    updated = _put_profile(client, alice["headers"])
    assert updated.status_code == 200
    body = updated.json()
    assert body["headline"] == "Backend / AI Engineer"
    assert body["skills"] == ["Python", "FastAPI"]
    assert body["social_links"]["github"] == "https://github.com/alice"
    assert body["is_published"] is False

    published = _put_profile(client, alice["headers"], is_published=True)
    assert published.json()["is_published"] is True
    unpublished = _put_profile(client, alice["headers"], is_published=False)
    assert unpublished.json()["is_published"] is False


def test_profile_requires_auth(client):
    assert client.get("/api/portfolio-cms/profile").status_code == 401
    assert client.put("/api/portfolio-cms/profile", json={}).status_code == 401


def test_profile_is_per_user(client, make_user):
    alice = make_user("alice")
    bob = make_user("bob")
    _put_profile(client, alice["headers"], headline="Alice headline")
    _put_profile(client, bob["headers"], headline="Bob headline")
    assert _profile(client, alice["headers"]).json()["headline"] == "Alice headline"
    assert _profile(client, bob["headers"]).json()["headline"] == "Bob headline"


# --- projects CRUD ---------------------------------------------------------


def test_project_create_list_update_delete(client, make_user):
    alice = make_user("alice")
    created = _post_project(client, alice["headers"])
    assert created.status_code == 200
    project = created.json()
    assert project["id"] >= 1
    assert project["order_index"] == 1
    assert project["repository"] is None

    listed = client.get("/api/portfolio-cms/projects", headers=alice["headers"])
    assert [p["id"] for p in listed.json()] == [project["id"]]

    updated = client.put(
        f"/api/portfolio-cms/projects/{project['id']}",
        json={**project, "title": "Renamed", "is_visible": False},
        headers=alice["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Renamed"
    assert updated.json()["is_visible"] is False

    deleted = client.delete(f"/api/portfolio-cms/projects/{project['id']}", headers=alice["headers"])
    assert deleted.status_code == 200
    assert client.get("/api/portfolio-cms/projects", headers=alice["headers"]).json() == []


def test_project_requires_auth(client, make_user):
    alice = make_user("alice")
    assert client.get("/api/portfolio-cms/projects").status_code == 401
    assert client.post("/api/portfolio-cms/projects", json={"title": "x"}).status_code == 401
    assert client.put("/api/portfolio-cms/projects/1", json={"title": "x"}).status_code == 401
    assert client.delete("/api/portfolio-cms/projects/1").status_code == 401


def test_project_isolation_between_users(client, make_user):
    alice = make_user("alice")
    bob = make_user("bob")
    project_id = _post_project(client, alice["headers"]).json()["id"]

    assert client.put(
        f"/api/portfolio-cms/projects/{project_id}", json={"title": "hijack"}, headers=bob["headers"]
    ).status_code == 404
    assert client.delete(
        f"/api/portfolio-cms/projects/{project_id}", headers=bob["headers"]
    ).status_code == 404
    assert client.get("/api/portfolio-cms/projects", headers=bob["headers"]).json() == []


def test_project_repository_binding_must_be_own_repo(client, make_user):
    alice = make_user("alice")
    bob = make_user("bob")
    bob_repo = _insert_repo(bob["user"]["id"], "bob-repo", 1)

    assert _post_project(client, alice["headers"], repository_id=bob_repo).status_code == 404

    alice_repo = _insert_repo(alice["user"]["id"], "alice-repo", 1)
    ok = _post_project(client, alice["headers"], repository_id=alice_repo)
    assert ok.status_code == 200
    assert ok.json()["repository"]["name"] == "alice-repo"


def test_project_count_cap(client, make_user):
    alice = make_user("alice")
    for index in range(30):
        response = _post_project(client, alice["headers"], title=f"p{index}")
        assert response.status_code == 200
    assert _post_project(client, alice["headers"], title="overflow").status_code == 400


def test_project_ordering_full_set_required(client, make_user):
    alice = make_user("alice")
    first = _post_project(client, alice["headers"], title="first").json()
    second = _post_project(client, alice["headers"], title="second").json()

    partial = client.put(
        "/api/portfolio-cms/projects/order", json={"ids": [first["id"]]}, headers=alice["headers"]
    )
    assert partial.status_code == 400

    reordered = client.put(
        "/api/portfolio-cms/projects/order", json={"ids": [second["id"], first["id"]]}, headers=alice["headers"]
    )
    assert reordered.status_code == 200
    titles = [project["title"] for project in reordered.json()]
    assert titles == ["second", "first"]
    orders = [project["order_index"] for project in reordered.json()]
    assert orders == [1, 2]


def test_project_order_requires_auth_and_ownership(client, make_user):
    alice = make_user("alice")
    bob = make_user("bob")
    project_id = _post_project(client, alice["headers"]).json()["id"]
    assert client.put("/api/portfolio-cms/projects/order", json={"ids": [project_id]}).status_code == 401
    assert client.put(
        "/api/portfolio-cms/projects/order", json={"ids": [project_id]}, headers=bob["headers"]
    ).status_code == 400


# --- public view -----------------------------------------------------------


def test_public_view_unpublished_keeps_legacy_shape(client, make_user):
    alice = make_user("alice")
    _put_profile(client, alice["headers"])  # configured but not published
    _post_project(client, alice["headers"], title="Secret WIP")

    body = client.get("/api/portfolio/alice").json()
    assert "cms" not in body
    assert set(body) == {
        "slug", "name", "title", "summary", "skills", "projects", "repositories", "latest_interview_score",
    }
    assert [p["name"] for p in body["projects"]] != ["Secret WIP"]


def test_public_view_published_renders_cms_content(client, make_user):
    alice = make_user("alice")
    repo = _insert_repo(alice["user"]["id"], "cms-repo", 1)
    _put_profile(client, alice["headers"], is_published=True)
    _post_project(client, alice["headers"], title="Showcased", repository_id=repo)
    _post_project(client, alice["headers"], title="Hidden", is_visible=False)

    body = client.get("/api/portfolio/alice").json()
    assert body["cms"] is True
    assert body["name"] == "Alice"
    assert body["title"] == "Backend / AI Engineer"
    assert body["resume_url"] == "https://example.com/resume.pdf"
    assert body["social"] == {"github": "https://github.com/alice", "blog": "https://alice.dev"}
    assert [p["name"] for p in body["projects"]] == ["Showcased"]
    project = body["projects"][0]
    assert project["repository"]["name"] == "cms-repo"
    assert project["decisions"] == "用户代码只进独立 Runner。"
    # repositories section still governed by the repository is_public flag
    assert [r["name"] for r in body["repositories"]] == ["cms-repo"]


def test_public_view_bound_private_repo_not_revealed(client, make_user):
    alice = make_user("alice")
    private_repo = _insert_repo(alice["user"]["id"], "secret-repo", 0, is_private=1)
    _put_profile(client, alice["headers"], is_published=True)
    project = _post_project(client, alice["headers"], title="Bound", repository_id=private_repo).json()

    # owner sees the binding in the editor (own data)...
    assert project["repository"]["name"] == "secret-repo"
    # ...but the public view never reveals a non-public repository
    body = client.get("/api/portfolio/alice").json()
    assert body["projects"][0]["repository"] is None
    assert "secret-repo" not in str(body["repositories"])
    assert "https://github.com/user/secret-repo" not in str(body)


def test_public_view_ordering_respected(client, make_user):
    alice = make_user("alice")
    _put_profile(client, alice["headers"], is_published=True)
    first = _post_project(client, alice["headers"], title="A").json()
    second = _post_project(client, alice["headers"], title="B").json()
    client.put(
        "/api/portfolio-cms/projects/order", json={"ids": [second["id"], first["id"]]}, headers=alice["headers"]
    )
    body = client.get("/api/portfolio/alice").json()
    assert [p["name"] for p in body["projects"]] == ["B", "A"]


def test_public_view_no_private_learning_data(client, make_user):
    alice = make_user("alice")
    session_id = client.post("/api/interviews", json={}, headers=alice["headers"]).json()["id"]
    client.post(
        f"/api/interviews/{session_id}/turn",
        json={"interviewer_prompt": "介绍你自己", "answer": "我是后端工程师，擅长 FastAPI 与异步系统。"},
        headers=alice["headers"],
    )
    client.post(
        f"/api/interviews/{session_id}/recording",
        content=b"secret-audio",
        headers={**alice["headers"], "Content-Type": "audio/webm"},
    )
    _put_profile(client, alice["headers"], is_published=True)
    _post_project(client, alice["headers"], title="Showcased")

    body = client.get("/api/portfolio/alice").json()
    serialized = str(body).lower()
    for forbidden in ("wrong", "mastery", "weakness", "answer", "recording", "transcript", "password", "secret-audio"):
        assert forbidden not in serialized, f"published portfolio leaked private field: {forbidden}"
    assert "我是后端工程师" not in str(body)
    assert isinstance(body["latest_interview_score"], (int, float))


def test_public_view_unknown_user_404(client):
    assert client.get("/api/portfolio/ghost").status_code == 404
