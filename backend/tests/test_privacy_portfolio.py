"""Privacy regression: the public portfolio is anonymous-accessible but must
only expose repos the owner explicitly made public, and must never leak
private learning data (wrong book, mastery, answers, recordings, transcripts).
Hidden coding tests must never be returned to the client.
"""
from __future__ import annotations

from tests.conftest import db_insert


def _insert_repo(user_id: int, name: str, is_public: int) -> int:
    return db_insert(
        "INSERT INTO repositories (user_id, provider, name, url, branch, last_commit, file_count, summary, "
        "is_public, synced_at) VALUES (?, 'github', ?, ?, 'main', 'abc123', 2, '{}', ?, datetime('now'))",
        (user_id, name, f"https://github.com/user/{name}", is_public),
    )


def test_portfolio_anonymous_and_public_only(client, make_user):
    alice = make_user("alice")
    _insert_repo(alice["user"]["id"], "alice-public-repo", 1)
    _insert_repo(alice["user"]["id"], "alice-private-repo", 0)

    response = client.get("/api/portfolio/alice")
    assert response.status_code == 200
    body = response.json()

    repo_names = [repo["name"] for repo in body["repositories"]]
    assert repo_names == ["alice-public-repo"], "portfolio must only list explicitly public repos"

    allowed_top_level = {
        "slug", "name", "title", "summary", "skills", "projects", "repositories", "latest_interview_score",
    }
    assert set(body) == allowed_top_level, f"unexpected portfolio fields: {set(body) - allowed_top_level}"

    serialized = str(body).lower()
    for forbidden in ("wrong", "mastery", "weakness", "answer", "recording", "transcript", "password"):
        assert forbidden not in serialized, f"portfolio leaked private field: {forbidden}"


def test_portfolio_visibility_toggle_controls_exposure(client, make_user):
    alice = make_user("alice")
    repo_id = _insert_repo(alice["user"]["id"], "toggle-repo", 0)

    assert client.get("/api/portfolio/alice").json()["repositories"] == []

    toggled = client.patch(f"/api/repos/{repo_id}/visibility", json={"is_public": True}, headers=alice["headers"])
    assert toggled.status_code == 200
    assert toggled.json()["is_public"] is True
    assert [r["name"] for r in client.get("/api/portfolio/alice").json()["repositories"]] == ["toggle-repo"]

    off = client.patch(f"/api/repos/{repo_id}/visibility", json={"is_public": False}, headers=alice["headers"])
    assert off.status_code == 200
    assert client.get("/api/portfolio/alice").json()["repositories"] == []


def test_portfolio_unknown_user_404(client):
    assert client.get("/api/portfolio/ghost").status_code == 404


def test_portfolio_latest_score_aggregate_only(client, make_user):
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

    body = client.get("/api/portfolio/alice").json()
    assert isinstance(body["latest_interview_score"], (int, float))
    assert "secret-audio" not in str(body)
    assert "我是后端工程师" not in str(body)


def test_hidden_tests_never_leaked(client, make_user):
    alice = make_user("alice")

    listing = client.get("/api/coding/challenges", headers=alice["headers"])
    assert listing.status_code == 200
    assert "hidden_tests" not in listing.text
    assert "reference_solution" not in listing.text

    for challenge in listing.json():
        assert set(challenge) == {
            "id", "slug", "title", "category", "difficulty", "description", "function_name",
            "starter_code", "public_tests", "hints", "tags", "solved", "wrongbook",
        }

    detail = client.get(f"/api/coding/challenges/{listing.json()[0]['id']}", headers=alice["headers"])
    assert detail.status_code == 200
    assert "hidden_tests" not in detail.text
    assert "reference_solution" not in detail.text
