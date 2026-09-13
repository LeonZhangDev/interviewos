"""v1.0 Observability tests: request ids, structured access logs, /ready,
/metrics, the audit trail and the optional error-tracking hook.

The suite runs offline (SQLite + a closed Redis port), so /ready's cache
check fails by default — exactly the degraded state the endpoint must
report without leaking internals.
"""
from __future__ import annotations

import json
import logging
import sys

import pytest

from app.observability import JsonFormatter, audit, init_error_tracking

from .conftest import db_insert, db_scalar

_LOGGERS = ("interviewos.access", "interviewos.audit", "interviewos.observability")


@pytest.fixture()
def capture_logs():
    """Own handler attached directly to the interviewos loggers: they do not
    propagate to the root logger (uvicorn would double-print), so root-based
    capture like pytest's caplog cannot be relied on here."""
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    attached = []
    for name in _LOGGERS:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # In-process alembic runs call fileConfig, whose default
        # disable_existing_loggers=True would silently flip this flag and
        # swallow every record (env.py disables that, this is insurance).
        logger.disabled = False
        attached.append(logger)
    yield records
    for logger in attached:
        logger.removeHandler(handler)


def _records(records: list[logging.LogRecord], name: str) -> list[logging.LogRecord]:
    return [r for r in records if r.name == name]


def _record_json(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


class TestRequestId:
    def test_generates_a_request_id_when_absent(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID")

    def test_propagates_an_incoming_request_id(self, client):
        response = client.get("/health", headers={"X-Request-ID": "trace-1234"})
        assert response.headers["X-Request-ID"] == "trace-1234"

    def test_unauthorized_requests_still_carry_a_request_id(self, client):
        response = client.get("/api/dashboard")
        assert response.status_code == 401
        assert response.headers.get("X-Request-ID")


class TestAccessLog:
    def test_emits_one_structured_line_per_request(self, client, capture_logs):
        response = client.get(
            "/api/dashboard",
            headers={"X-Request-ID": "access-log-1"},
        )
        assert response.status_code == 401
        records = _records(capture_logs, "interviewos.access")
        assert len(records) == 1
        payload = _record_json(records[0])
        assert payload["event"] == "access"
        assert payload["request_id"] == "access-log-1"
        assert payload["method"] == "GET"
        assert payload["path"] == "/api/dashboard"
        assert payload["status"] == 401
        assert isinstance(payload["duration_ms"], (int, float))
        assert payload["user"] is None  # no token -> no subject

    def test_authenticated_request_logs_the_user(self, client, make_user, capture_logs):
        user = make_user()
        assert client.get("/api/dashboard", headers=user["headers"]).status_code == 200
        payload = _record_json(_records(capture_logs, "interviewos.access")[-1])
        assert payload["user"] == user["username"]
        assert payload["status"] == 200

    def test_access_log_never_contains_credentials(self, client, make_user, capture_logs):
        user = make_user(password="super-secret-pass-1")
        response = client.post(
            "/api/auth/login",
            json={"identity": user["username"], "password": "super-secret-pass-1"},
        )
        assert response.status_code == 200
        blob = "".join(JsonFormatter().format(r) for r in capture_logs)
        assert "super-secret-pass-1" not in blob
        assert user["access_token"] not in blob
        assert user["refresh_token"] not in blob


class TestReadiness:
    def test_reports_not_ready_when_cache_is_down(self, client):
        # conftest points Redis at a closed port: database healthy, cache not.
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"] == {"database": True, "cache": False}

    def test_reports_ready_when_dependencies_answer(self, client, monkeypatch):
        import app.main as main_module

        async def fake_ping():
            return True

        monkeypatch.setattr(main_module.redis, "ping", fake_ping)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": True, "cache": True}}

    def test_failure_details_stay_out_of_the_response(self, client):
        response = client.get("/ready")
        blob = response.text
        for leak in ("6399", "ConnectionRefused", "Traceback", "redis://"):
            assert leak not in blob

    def test_readiness_is_public(self, client):
        assert client.get("/ready").status_code in (200, 503)  # no 401


class TestMetrics:
    def test_metrics_endpoint_is_public_and_exposes_counters(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "interviewos_http_requests_total" in response.text
        assert "interviewos_http_request_duration_seconds" in response.text

    def test_requests_are_counted_with_route_templates(self, client, make_user):
        user = make_user()
        response = client.get("/api/questions", headers=user["headers"])
        assert response.status_code == 200
        metrics = client.get("/metrics")
        assert 'route="/api/questions"' in metrics.text

    def test_health_probes_are_not_counted(self, client):
        before = client.get("/metrics").text.count('route="/health"')
        client.get("/health")
        client.get("/health")
        after = client.get("/metrics").text.count('route="/health"')
        assert before == after


class TestAuditTrail:
    def test_register_and_login_are_audited(self, client, make_user, capture_logs):
        user = make_user()
        response = client.post(
            "/api/auth/login",
            json={"identity": user["username"], "password": user["password"]},
        )
        assert response.status_code == 200
        records = _records(capture_logs, "interviewos.audit")
        actions = [r.action for r in records]
        assert "auth.register" in actions
        assert "auth.login" in actions
        login = next(r for r in records if r.action == "auth.login")
        assert login.user_id == user["user"]["id"]
        assert login.username == user["username"]
        assert login.event == "audit"
        assert login.request_id  # joined with the access log via contextvar

    def test_failed_login_is_audited_without_the_password(self, client, capture_logs):
        response = client.post(
            "/api/auth/login",
            json={"identity": "ghost-user", "password": "wrong-secret-pass"},
        )
        assert response.status_code == 401
        records = _records(capture_logs, "interviewos.audit")
        failed = next(r for r in records if r.action == "auth.login_failed")
        assert failed.username == "ghost-user"
        assert failed.user_id is None
        blob = "".join(JsonFormatter().format(r) for r in records)
        assert "wrong-secret-pass" not in blob

    def test_logout_revocation_paths_are_both_audited(self, client, make_user, capture_logs):
        user = make_user()
        response = client.post(
            "/api/auth/logout",
            json={"refresh_token": user["refresh_token"], "all_devices": True},
            headers=user["headers"],
        )
        assert response.status_code == 200
        records = _records(capture_logs, "interviewos.audit")
        # One request walks both revocation paths: the presented refresh token
        # and the all-devices watermark. Two records, both metadata-only.
        logouts = [r for r in records if r.action == "auth.logout"]
        assert {(r.user_id, r.all_devices) for r in logouts} == {
            (user["user"]["id"], False),
            (user["user"]["id"], True),
        }

    def test_change_password_is_audited(self, client, make_user, capture_logs):
        user = make_user()
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": user["password"], "new_password": "brand-new-pass-456"},
            headers=user["headers"],
        )
        assert response.status_code == 200
        record = next(r for r in _records(capture_logs, "interviewos.audit") if r.action == "auth.change_password")
        assert record.username == user["username"]
        blob = "".join(JsonFormatter().format(r) for r in capture_logs)
        assert "brand-new-pass-456" not in blob

    def test_playground_session_creation_is_audited(self, client, make_user, capture_logs):
        user = make_user()
        response = client.post(
            "/api/playground/sessions",
            json={"kind": "sql"},
            headers=user["headers"],
        )
        assert response.status_code == 200
        record = next(r for r in _records(capture_logs, "interviewos.audit") if r.action == "playground.session_created")
        assert record.kind == "sql"
        assert record.user_id == user["user"]["id"]

    def test_git_disconnect_is_audited(self, client, make_user, capture_logs):
        user = make_user()
        db_insert(
            "INSERT INTO git_connections "
            "(user_id, provider, provider_login, provider_user_id, access_token_encrypted, scopes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (user["user"]["id"], "github", "alice", "42", "ciphertext-blob", "repo"),
        )
        assert db_scalar("SELECT COUNT(*) FROM git_connections WHERE user_id = ?", (user["user"]["id"],)) == 1
        response = client.delete("/api/git/github", headers=user["headers"])
        assert response.status_code == 200
        record = next(r for r in _records(capture_logs, "interviewos.audit") if r.action == "git.disconnected")
        assert record.provider == "github"
        assert record.username == user["username"]
        blob = "".join(JsonFormatter().format(r) for r in capture_logs)
        assert "ciphertext-blob" not in blob  # the stored token never reaches logs

    def test_audit_helper_accepts_metadata_only(self, capture_logs):
        audit("custom.action", user_id=7, username="alice", provider="github", files=3)
        record = _records(capture_logs, "interviewos.audit")[-1]
        assert record.action == "custom.action"
        assert record.provider == "github"
        assert record.files == 3


class TestErrorTrackingHook:
    def test_blank_dsn_is_a_noop(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "sentry_dsn", "")
        init_error_tracking()  # must not raise or import anything

    def test_dsn_without_sdk_warns_instead_of_crashing(self, monkeypatch, capture_logs):
        from app.config import settings

        monkeypatch.setattr(settings, "sentry_dsn", "https://public@sentry.example.com/1")
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # force ImportError
        init_error_tracking()  # must not raise
        warnings = _records(capture_logs, "interviewos.observability")
        assert any("sentry-sdk" in r.getMessage() for r in warnings)


class TestJsonFormatter:
    def test_output_is_one_parseable_json_line(self):
        record = logging.LogRecord(
            name="interviewos.audit", level=logging.INFO, pathname=__file__,
            lineno=1, msg="auth.login", args=(), exc_info=None,
        )
        record.action = "auth.login"
        record.user_id = 1
        payload = json.loads(JsonFormatter().format(record))
        assert payload["logger"] == "interviewos.audit"
        assert payload["message"] == "auth.login"
        assert payload["action"] == "auth.login"
        assert payload["user_id"] == 1
