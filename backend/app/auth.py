from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request

from .config import settings


PBKDF2_ROUNDS = 240_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            _b64url_decode(salt),
            int(rounds),
        )
        return hmac.compare_digest(actual, _b64url_decode(digest))
    except (TypeError, ValueError):
        return False


def create_access_token(subject: str, *, expires_minutes: int | None = None, issued_at: datetime | None = None) -> str:
    now = issued_at or datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes or settings.auth_token_minutes)
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "interviewos",
    }
    head = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    signature = hmac.new(settings.auth_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        head, body, signature = token.split(".")
        signing_input = f"{head}.{body}".encode()
        expected = hmac.new(settings.auth_secret.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(body))
        if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        if payload.get("iss") != "interviewos" or not payload.get("sub"):
            raise ValueError("bad claims")
        return payload
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token")


def bearer_subject(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return str(decode_access_token(header[7:].strip())["sub"])


def bearer_payload(request: Request) -> dict[str, Any]:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return decode_access_token(header[7:].strip())


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
