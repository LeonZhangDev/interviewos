"""v1.0 Git provider integrations: OAuth state lifecycle, encrypted token
storage, provider repository listing, token-authenticated private repo sync
and cross-user isolation. All provider HTTP calls are monkeypatched — the
suite never touches github.com / gitee.com."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from app import git_routes, main
from app.timeutil import utc_now
from app.git_oauth import GitProviderError, decrypt_token, encrypt_token
from tests.conftest import DB_PATH, db_scalar


# --- token encryption (unit) -------------------------------------------------


def test_encrypt_token_roundtrip_without_plaintext():
    blob = encrypt_token("gho_secret-provider-token-123")
    assert blob != "gho_secret-provider-token-123"
    assert "gho_secret-provider-token-123" not in blob
    assert decrypt_token(blob) == "gho_secret-provider-token-123"


def test_encrypt_token_is_randomized_and_tamper_evident():
    first = encrypt_token("same-token")
    second = encrypt_token("same-token")
    assert first != second  # random salt + nonce per record
    assert decrypt_token(first) == decrypt_token(second) == "same-token"
    tampered = first[:-6] + ("AAAAAA" if not first.endswith("AAAAAA") else "BBBBBB")
    with pytest.raises(ValueError):
        decrypt_token(tampered)
    with pytest.raises(ValueError):
        decrypt_token("not-a-valid-blob")


def test_encrypt_token_key_isolation(monkeypatch):
    from app.config import settings

    blob = encrypt_token("token-under-old-key")
    monkeypatch.setattr(settings, "oauth_encryption_key", "a-completely-different-key")
    with pytest.raises(ValueError):
        decrypt_token(blob)


# --- API surface ------------------------------------------------------------


def test_git_routes_require_authentication(client):
    assert client.get("/api/git/providers").status_code == 401
    assert client.post("/api/git/github/authorize").status_code == 401
    assert client.post("/api/git/callback", json={"code": "c", "state": "s" * 12}).status_code == 401


def test_provider_status_reports_configuration(client, make_user):
    user = make_user()
    response = client.get("/api/git/providers", headers=user["headers"])
    assert response.status_code == 200
    providers = {item["provider"]: item for item in response.json()}
    assert set(providers) == {"github", "gitee"}
    assert providers["github"]["configured"] is True
    assert providers["github"]["connected"] is False
    assert providers["gitee"]["configured"] is True


def test_provider_status_when_unconfigured(client, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "github_client_id", "")
    user = make_user()
    response = client.get("/api/git/providers", headers=user["headers"])
    providers = {item["provider"]: item for item in response.json()}
    assert providers["github"]["configured"] is False

    refused = client.post("/api/git/github/authorize", headers=user["headers"])
    assert refused.status_code == 400
    assert "GITHUB_CLIENT_ID" in refused.json()["detail"]


def test_authorize_unknown_provider_404(client, make_user):
    user = make_user()
    assert client.post("/api/git/gitlab/authorize", headers=user["headers"]).status_code == 404


def test_authorize_creates_state_and_url(client, make_user):
    user = make_user()
    response = client.post("/api/git/github/authorize", headers=user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "github"
    assert body["authorize_url"].startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-github-client-id" in body["authorize_url"]
    assert f"state={body['state']}" in body["authorize_url"]
    assert "read%3Auser" in body["authorize_url"] or "read:user" in body["authorize_url"]
    assert db_scalar("SELECT COUNT(*) FROM oauth_states WHERE state = ?", (body["state"],)) == 1


def test_gitee_authorize_url_shape(client, make_user):
    user = make_user()
    response = client.post("/api/git/gitee/authorize", headers=user["headers"])
    body = response.json()
    assert body["authorize_url"].startswith("https://gitee.com/oauth/authorize")
    assert "response_type=code" in body["authorize_url"]


@pytest.fixture()
def fake_provider(monkeypatch):
    """Monkeypatch the provider HTTP helpers used by git_routes."""
    calls: dict[str, dict] = {}

    async def fake_exchange(provider: str, code: str):
        calls["exchange"] = {"provider": provider, "code": code}
        if code == "bad-code":
            raise GitProviderError("bad verification code")
        return {"access_token": f"tok-{provider}-{code}", "scope": "read:user repo", "token_type": "bearer"}

    async def fake_user(provider: str, access_token: str):
        calls["user"] = {"provider": provider, "access_token": access_token}
        return {"login": f"{provider}-octocat", "id": "4242", "name": "Octo Cat"}

    async def fake_repos(provider: str, access_token: str, *, visibility: str = "all", page: int = 1, per_page: int = 30):
        calls["repos"] = {"provider": provider, "access_token": access_token, "visibility": visibility}
        return [
            {"name": "octocat/public-app", "private": False, "default_branch": "main",
             "updated_at": "2026-09-01T10:00:00Z", "url": "https://github.com/octocat/public-app", "description": "demo"},
            {"name": "octocat/secret-service", "private": True, "default_branch": "master",
             "updated_at": "2026-09-08T10:00:00Z", "url": "https://github.com/octocat/secret-service", "description": ""},
        ]

    monkeypatch.setattr(git_routes, "exchange_code", fake_exchange)
    monkeypatch.setattr(git_routes, "fetch_provider_user", fake_user)
    monkeypatch.setattr(git_routes, "list_provider_repos", fake_repos)
    return calls


def _authorize(client, user, provider="github") -> str:
    response = client.post(f"/api/git/{provider}/authorize", headers=user["headers"])
    assert response.status_code == 200
    return response.json()["state"]


def _complete_callback(client, user, state: str, code: str = "authcode1"):
    return client.post("/api/git/callback", json={"code": code, "state": state}, headers=user["headers"])


def test_callback_creates_encrypted_connection(client, make_user, fake_provider):
    user = make_user()
    state = _authorize(client, user)
    response = _complete_callback(client, user, state)
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["login"] == "github-octocat"
    assert "tok-github" not in response.text  # token never leaves the backend

    encrypted = db_scalar("SELECT access_token_encrypted FROM git_connections WHERE provider = 'github'")
    assert encrypted and "tok-github-authcode1" not in encrypted
    assert decrypt_token(encrypted) == "tok-github-authcode1"

    status = client.get("/api/git/providers", headers=user["headers"]).json()
    github = next(item for item in status if item["provider"] == "github")
    assert github["connected"] is True and github["login"] == "github-octocat"


def test_callback_reconnect_overwrites_token(client, make_user, fake_provider):
    user = make_user()
    first = _complete_callback(client, user, _authorize(client, user), code="first-code")
    assert first.status_code == 200
    second = _complete_callback(client, user, _authorize(client, user), code="second-code")
    assert second.status_code == 200
    assert db_scalar("SELECT COUNT(*) FROM git_connections WHERE provider = 'github'") == 1
    encrypted = db_scalar("SELECT access_token_encrypted FROM git_connections WHERE provider = 'github'")
    assert decrypt_token(encrypted) == "tok-github-second-code"


def test_callback_rejects_unknown_state(client, make_user):
    user = make_user()
    response = _complete_callback(client, user, "f" * 43)
    assert response.status_code == 400


def test_callback_state_is_single_use(client, make_user, fake_provider):
    user = make_user()
    state = _authorize(client, user)
    assert _complete_callback(client, user, state).status_code == 200
    assert _complete_callback(client, user, state).status_code == 400


def test_callback_state_is_user_bound(client, make_user, fake_provider):
    alice = make_user("alice")
    bob = make_user("bob")
    state = _authorize(client, alice)
    # Bob tries to complete Alice's authorization with his own session.
    response = _complete_callback(client, bob, state)
    assert response.status_code == 400
    assert db_scalar("SELECT COUNT(*) FROM git_connections") == 0


def test_callback_rejects_expired_state(client, make_user, fake_provider):
    user = make_user()
    state = _authorize(client, user)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    try:
        conn.execute(
            "UPDATE oauth_states SET expires_at = ? WHERE state = ?",
            ((utc_now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), state),
        )
        conn.commit()
    finally:
        conn.close()
    assert _complete_callback(client, user, state).status_code == 400


def test_callback_provider_error_becomes_502(client, make_user, fake_provider):
    user = make_user()
    state = _authorize(client, user)
    response = _complete_callback(client, user, state, code="bad-code")
    assert response.status_code == 502
    assert "bad verification code" in response.json()["detail"]
    assert db_scalar("SELECT COUNT(*) FROM git_connections") == 0


def test_provider_repos_listing_lifecycle(client, make_user, fake_provider):
    user = make_user()
    # Without a connection there is nothing to list with.
    assert client.get("/api/git/github/repos", headers=user["headers"]).status_code == 404

    _complete_callback(client, user, _authorize(client, user))
    response = client.get("/api/git/github/repos?visibility=private", headers=user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "github" and body["visibility"] == "private"
    names = [item["name"] for item in body["repos"]]
    assert "octocat/secret-service" in names
    assert fake_provider["repos"]["access_token"] == "tok-github-authcode1"

    assert client.get("/api/git/github/repos?visibility=everything", headers=user["headers"]).status_code == 422


def test_disconnect_removes_connection(client, make_user, fake_provider):
    user = make_user()
    _complete_callback(client, user, _authorize(client, user))
    assert client.delete("/api/git/github", headers=user["headers"]).status_code == 200
    assert db_scalar("SELECT COUNT(*) FROM git_connections") == 0
    status = client.get("/api/git/providers", headers=user["headers"]).json()
    assert next(item for item in status if item["provider"] == "github")["connected"] is False
    # Second disconnect has nothing to remove.
    assert client.delete("/api/git/github", headers=user["headers"]).status_code == 404


def test_connections_are_user_scoped(client, make_user, fake_provider):
    alice = make_user("alice")
    bob = make_user("bob")
    _complete_callback(client, alice, _authorize(client, alice))
    status = client.get("/api/git/providers", headers=bob["headers"]).json()
    assert all(item["connected"] is False for item in status)
    assert client.get("/api/git/github/repos", headers=bob["headers"]).status_code == 404
    assert client.delete("/api/git/github", headers=bob["headers"]).status_code == 404


# --- private repository sync uses the stored token ---------------------------


def _fake_scan_result(name="octocat/secret-service", commit="abc123def456"):
    return {
        "url": f"https://github.com/{name}",
        "name": name,
        "branch": "master",
        "commit": commit,
        "files": [
            {"path": "app.py", "language": "Python", "size": 20, "content": "print('hi')",
             "symbols": "[]", "knowledge": "[]", "questions": "[]"},
        ],
        "summary": {"languages": [["Python", 1]], "topics": [], "commit_message": "init",
                    "diff": {"available": False, "changed": False, "files": [], "questions": []}},
    }


def test_sync_passes_connection_token_and_persists_private_flag(client, make_user, fake_provider, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_clone(provider, repo, branch, max_files=260, previous_commit="", access_token=""):
        captured.update(provider=provider, repo=repo, access_token=access_token)
        return _fake_scan_result()

    monkeypatch.setattr(main, "clone_and_scan", fake_clone)
    user = make_user()
    _complete_callback(client, user, _authorize(client, user))

    response = client.post(
        "/api/repos/sync",
        json={"provider": "github", "repo": "octocat/secret-service", "branch": "master", "is_private": True},
        headers=user["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_private"] is True
    assert captured["access_token"] == "tok-github-authcode1"
    assert db_scalar("SELECT is_private FROM repositories WHERE name = ?", ("octocat/secret-service",)) == 1


def test_sync_without_connection_stays_anonymous(client, make_user, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_clone(provider, repo, branch, max_files=260, previous_commit="", access_token=""):
        captured["access_token"] = access_token
        return _fake_scan_result(name="octocat/public-app")

    monkeypatch.setattr(main, "clone_and_scan", fake_clone)
    user = make_user()
    response = client.post(
        "/api/repos/sync",
        json={"provider": "github", "repo": "octocat/public-app", "branch": "master"},
        headers=user["headers"],
    )
    assert response.status_code == 200
    assert captured["access_token"] == ""
    assert response.json()["is_private"] is False


def test_sync_with_undecryptable_token_returns_400(client, make_user, fake_provider, monkeypatch):
    from app.config import settings

    user = make_user()
    _complete_callback(client, user, _authorize(client, user))
    # Simulate a rotated encryption key: the stored blob can no longer decrypt.
    monkeypatch.setattr(settings, "oauth_encryption_key", "rotated-away-from-original")
    response = client.post(
        "/api/repos/sync",
        json={"provider": "github", "repo": "octocat/secret-service", "branch": "master"},
        headers=user["headers"],
    )
    assert response.status_code == 400
    assert "authorize it again" in response.json()["detail"]


def test_sync_does_not_leak_token_in_git_errors(monkeypatch):
    import asyncio

    import app.repo_sync as repo_sync_module

    async def failing_cmd(*args, **kwargs):
        raise RuntimeError(
            "fatal: repository 'https://x-access-token:tok-github-authcode1@github.com/octocat/secret-service.git/' not found"
        )

    monkeypatch.setattr(repo_sync_module, "_cmd", failing_cmd)
    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(
            repo_sync_module.clone_and_scan(
                "github", "octocat/secret-service", "master", access_token="tok-github-authcode1"
            )
        )
    assert "tok-github-authcode1" not in str(excinfo.value)
    assert "***" in str(excinfo.value)


def test_clone_url_uses_provider_specific_credentials():
    from app.repo_sync import _clone_url

    assert _clone_url("github", "o/r", "https://github.com/o/r", "") == "https://github.com/o/r.git"
    assert (
        _clone_url("github", "o/r", "https://github.com/o/r", "tok")
        == "https://x-access-token:tok@github.com/o/r.git"
    )
    assert _clone_url("gitee", "o/r", "https://gitee.com/o/r", "tok") == "https://oauth2:tok@gitee.com/o/r.git"
