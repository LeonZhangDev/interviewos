"""Auth lifecycle: register / login / refresh rotation / logout revocation /
change-password, plus the JWT guard on private workbench APIs.
"""
from __future__ import annotations


def test_register_login_me(client, make_user):
    user = make_user("alice")

    me = client.get("/api/auth/me", headers=user["headers"])
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert me.json()["email"] == "alice@example.com"

    login = client.post("/api/auth/login", json={"identity": "alice", "password": user["password"]})
    assert login.status_code == 200
    body = login.json()
    assert body["access_token"] and body["refresh_token"]
    me_via_login = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me_via_login.status_code == 200

    email_login = client.post("/api/auth/login", json={"identity": "alice@example.com", "password": user["password"]})
    assert email_login.status_code == 200


def test_register_rejects_duplicates_and_bad_input(client, make_user):
    make_user("alice")
    dup = client.post("/api/auth/register", json={
        "username": "alice", "email": "other@example.com", "password": "secret-pass-123",
    })
    assert dup.status_code == 409

    dup_email = client.post("/api/auth/register", json={
        "username": "alice2", "email": "alice@example.com", "password": "secret-pass-123",
    })
    assert dup_email.status_code == 409

    bad_email = client.post("/api/auth/register", json={
        "username": "carol", "email": "not-an-email", "password": "secret-pass-123",
    })
    assert bad_email.status_code == 422

    short_password = client.post("/api/auth/register", json={
        "username": "carol", "email": "carol@example.com", "password": "short",
    })
    assert short_password.status_code == 422


def test_login_wrong_password(client, make_user):
    make_user("alice")
    response = client.post("/api/auth/login", json={"identity": "alice", "password": "wrong-password-1"})
    assert response.status_code == 401


def test_me_requires_valid_token(client, make_user):
    make_user("alice")
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_guard_blocks_private_apis_without_token(client):
    assert client.get("/health").status_code == 200
    for path in ("/api/dashboard", "/api/questions", "/api/coding/wrongbook", "/api/knowledge-graph"):
        assert client.get(path).status_code == 401, path


def test_refresh_rotation(client, make_user):
    user = make_user("alice")

    first = client.post("/api/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert first.status_code == 200
    rotated = first.json()
    assert rotated["refresh_token"] != user["refresh_token"]
    assert rotated["access_token"]

    replay = client.post("/api/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert replay.status_code == 401, "old refresh token must be revoked after rotation"

    second = client.post("/api/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert second.status_code == 200

    garbage = client.post("/api/auth/refresh", json={"refresh_token": "x" * 48})
    assert garbage.status_code == 401


def test_logout_revokes_refresh_token(client, make_user):
    user = make_user("alice")
    response = client.post("/api/auth/logout", json={"refresh_token": user["refresh_token"]})
    assert response.status_code == 200
    refresh = client.post("/api/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert refresh.status_code == 401


def test_logout_all_devices_revokes_access_token(client, make_user):
    user = make_user("alice")
    response = client.post(
        "/api/auth/logout",
        json={"refresh_token": user["refresh_token"], "all_devices": True},
        headers=user["headers"],
    )
    assert response.status_code == 200

    me = client.get("/api/auth/me", headers=user["headers"])
    assert me.status_code == 401, "access token must die after all-devices logout"

    refresh = client.post("/api/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert refresh.status_code == 401


def test_change_password_full_cycle(client, make_user):
    user = make_user("alice")
    old_headers = user["headers"]
    old_refresh = user["refresh_token"]

    wrong_current = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password-9", "new_password": "brand-new-pass-456"},
        headers=old_headers,
    )
    assert wrong_current.status_code == 401

    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": user["password"], "new_password": "brand-new-pass-456"},
        headers=old_headers,
    )
    assert changed.status_code == 200
    new = changed.json()
    assert new["access_token"] and new["refresh_token"]

    assert client.get("/api/auth/me", headers=old_headers).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401

    new_headers = {"Authorization": f"Bearer {new['access_token']}"}
    assert client.get("/api/auth/me", headers=new_headers).status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200

    relogin = client.post("/api/auth/login", json={"identity": "alice", "password": "brand-new-pass-456"})
    assert relogin.status_code == 200
    old_login = client.post("/api/auth/login", json={"identity": "alice", "password": user["password"]})
    assert old_login.status_code == 401


def test_first_registration_claims_legacy_data(client, make_user):
    from tests.conftest import db_insert, db_scalar

    question_id = db_scalar("SELECT id FROM questions LIMIT 1")
    legacy_session_id = db_insert(
        "INSERT INTO interview_sessions (role, focus, difficulty, duration, script, created_at, user_id) "
        "VALUES ('AI Engineer', 'Python', 'medium', 45, '[]', datetime('now'), NULL)"
    )
    db_insert(
        "INSERT INTO interview_turns (session_id, user_id, question_id, interviewer_prompt, user_answer, "
        "score, feedback, followup, created_at) VALUES (?, NULL, NULL, 'legacy prompt', 'legacy answer', "
        "70, '', '', datetime('now'))",
        (legacy_session_id,),
    )
    legacy_answer_id = db_insert(
        "INSERT INTO answer_versions (question_id, user_id, content, score, created_at) "
        "VALUES (?, NULL, 'legacy answer body', 60, datetime('now'))",
        (question_id,),
    )

    user = make_user("alice")

    claimed_user = db_scalar("SELECT user_id FROM answer_versions WHERE id = ?", (legacy_answer_id,))
    assert claimed_user == user["user"]["id"], "first account must claim legacy single-user answers"

    answers = client.get(f"/api/questions/{question_id}/answers", headers=user["headers"])
    assert answers.status_code == 200
    assert len(answers.json()) == 1
    assert answers.json()[0]["content"] == "legacy answer body"

    history = client.get("/api/reports/history", headers=user["headers"])
    assert history.status_code == 200
    assert [row["session_id"] for row in history.json()] == [legacy_session_id]

    make_user("bob")
    still_alice = db_scalar("SELECT user_id FROM interview_turns WHERE session_id = ?", (legacy_session_id,))
    assert still_alice == user["user"]["id"], "later accounts must never re-claim data"
