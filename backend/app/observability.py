"""Observability primitives: structured JSON logs, request ids, Prometheus
metrics, a sensitive-operation audit trail and optional error tracking.

Everything here degrades to zero overhead when unconfigured: the app boots
and serves normally with no DSN, no collector and no structured-log
consumer. ``main.py`` guards the initialization call so even a total
failure inside this module cannot block startup (offline mode stays intact).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import settings

REQUEST_ID_HEADER = "X-Request-ID"

# Health probes and metric scrapes are infrastructure noise (compose pings
# /health every 5s); they are excluded from metrics and access logs but still
# get a request id in the response headers.
QUIET_PATHS = frozenset({"/health", "/ready", "/metrics"})

request_id_var: ContextVar[str | None] = ContextVar("interviewos_request_id", default=None)

_RESERVED_LOG_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per log line: ts/level/logger/message plus any extra
    fields the call site attached (request_id, user_id, ...)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging() -> None:
    """Attach the structured handler to the ``interviewos`` logger tree.

    Idempotent: only the first call installs anything, so repeated imports
    and TestClient lifecycles never stack duplicate handlers. uvicorn's own
    access/error loggers are intentionally left untouched.
    """
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if settings.log_format == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger = logging.getLogger("interviewos")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True


HTTP_REQUESTS_TOTAL = Counter(
    "interviewos_http_requests_total",
    "HTTP requests processed, labelled by method, route template and status",
    ["method", "route", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "interviewos_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def _route_label(request: Request) -> str:
    """Route templates ("/api/questions/{question_id}") keep label cardinality
    low; unmatched paths (scans, 404s, requests rejected before routing) all
    collapse to the single "unmatched" label."""
    route = request.scope.get("route")
    if route is not None:
        return getattr(route, "path", "unmatched")
    return "unmatched"


def _observe_request(request: Request, request_id: str, duration: float, status: int) -> None:
    route = _route_label(request)
    method = request.method
    if request.url.path not in QUIET_PATHS:
        HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=str(status)).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(duration)
    auth = getattr(request.state, "auth", None)
    logging.getLogger("interviewos.access").info(
        "request",
        extra={
            "event": "access",
            "request_id": request_id,
            "method": method,
            "path": request.url.path,
            "route": route,
            "status": status,
            "duration_ms": round(duration * 1000, 2),
            "user": auth.get("sub") if isinstance(auth, dict) else None,
        },
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Outermost app middleware: generates or propagates X-Request-ID, emits
    one structured access-log line and records Prometheus metrics per
    request. It wraps the JWT guard, so even 401 responses carry a request
    id and are measured."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            try:
                _observe_request(request, request_id, duration, status)
            except Exception:  # observability must never break a response
                logging.getLogger("interviewos.observability").debug(
                    "request observation failed", exc_info=True
                )
            request_id_var.reset(token)


def audit(action: str, *, user_id: int | None = None, username: str | None = None, **detail: object) -> None:
    """Append a sensitive-operation audit record (who / what / when only).

    Callers must pass metadata only — never tokens, passwords, OAuth codes or
    any other secret material; the payload is written verbatim to the log
    stream. ``detail`` carries action-specific metadata (provider, repo name,
    session kind, ...). The current request id is attached automatically when
    available so audit lines join with access logs.
    """
    logging.getLogger("interviewos.audit").info(
        action,
        extra={
            "event": "audit",
            "action": action,
            "user_id": user_id,
            "username": username,
            "request_id": request_id_var.get(),
            **detail,
        },
    )


def init_error_tracking() -> None:
    """Optional Sentry bootstrap. Zero overhead when SENTRY_DSN is blank (the
    default); sentry-sdk is deliberately not a hard dependency, so a set DSN
    without the package logs a warning instead of breaking startup."""
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger("interviewos.observability").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; error tracking stays disabled"
        )
        return
    sentry_sdk.init(dsn=dsn, environment="interviewos", traces_sample_rate=0.0)


def metrics_payload() -> tuple[bytes, str]:
    """(body, content-type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
