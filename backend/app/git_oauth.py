"""Git provider OAuth (GitHub / Gitee): authorize URLs, code exchange,
provider API access and at-rest encryption of provider access tokens.

Per AGENT.md/AGENT_PROMPT.md no new crypto framework dependency is allowed,
so the token store uses the same stdlib-only approach as the hand-rolled
JWT/PBKDF2 in app/auth.py:

- master secret = settings.oauth_encryption_key (or AUTH_SECRET fallback)
- per-record random 16-byte salt derives domain-separated enc/mac subkeys
- keystream = HMAC-SHA256(enc_key, nonce || counter) in CTR mode
- encrypt-then-MAC: HMAC-SHA256(mac_key, nonce || ciphertext), 16-byte tag

Provider access tokens never appear in API responses, logs or error
messages; repository sync errors are redacted in app/repo_sync.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import settings

PROVIDERS: dict[str, dict[str, str]] = {
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_url": "https://api.github.com/user",
        "repos_url": "https://api.github.com/user/repos",
        "scope": "read:user repo",
    },
    "gitee": {
        "authorize_url": "https://gitee.com/oauth/authorize",
        "token_url": "https://gitee.com/oauth/token",
        "user_url": "https://gitee.com/api/v5/user",
        "repos_url": "https://gitee.com/api/v5/user/repos",
        "scope": "user_info projects",
    },
}

_TOKEN_SCHEME = "gitenc"
_HTTP_TIMEOUT = httpx.Timeout(15.0)


class GitProviderError(Exception):
    """Provider-side failure with a sanitized, user-safe message."""


def _client_credentials(provider: str) -> tuple[str, str]:
    if provider == "github":
        return settings.github_client_id, settings.github_client_secret
    return settings.gitee_client_id, settings.gitee_client_secret


def provider_is_configured(provider: str) -> bool:
    client_id, client_secret = _client_credentials(provider)
    return bool(client_id and client_secret)


def oauth_redirect_uri() -> str:
    return settings.oauth_redirect_base.rstrip("/") + "/oauth/callback"


def build_authorize_url(provider: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    client_id, _ = _client_credentials(provider)
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": oauth_redirect_uri(),
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "github":
        params["allow_signup"] = "true"
    else:
        params["response_type"] = "code"
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def _json_or_error(response: httpx.Response, action: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code >= 400:
        detail = ""
        if isinstance(payload, dict):
            detail = str(payload.get("error") or payload.get("message") or "")
        raise GitProviderError(f"{action} failed: {detail[:200] or f'HTTP {response.status_code}'}")
    return payload if isinstance(payload, dict) else {}


async def exchange_code(provider: str, code: str) -> dict[str, Any]:
    """Exchange the OAuth authorization code for a provider access token."""
    cfg = PROVIDERS[provider]
    client_id, client_secret = _client_credentials(provider)
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": oauth_redirect_uri(),
    }
    if provider == "gitee":
        data["grant_type"] = "authorization_code"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            response = await client.post(cfg["token_url"], data=data, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise GitProviderError(f"token endpoint unreachable ({type(exc).__name__})") from exc
    payload = _json_or_error(response, "token exchange")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise GitProviderError("token endpoint returned no access_token")
    return payload


async def fetch_provider_user(provider: str, access_token: str) -> dict[str, str]:
    cfg = PROVIDERS[provider]
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            response = await client.get(
                cfg["user_url"],
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise GitProviderError(f"profile endpoint unreachable ({type(exc).__name__})") from exc
    payload = _json_or_error(response, "profile fetch")
    login = payload.get("login") or payload.get("username") or ""
    if not login:
        raise GitProviderError("profile endpoint returned no login")
    return {"login": str(login), "id": str(payload.get("id") or ""), "name": str(payload.get("name") or "")}


async def list_provider_repos(
    provider: str, access_token: str, *, visibility: str = "all", page: int = 1, per_page: int = 30
) -> list[dict[str, Any]]:
    """List repositories the token can access, normalized to a stable shape.

    Nothing is persisted here: the user explicitly picks which repositories
    to sync, so repos never chosen never enter the local database.
    """
    cfg = PROVIDERS[provider]
    params: dict[str, Any] = {"visibility": visibility, "page": page, "per_page": per_page}
    if provider == "github":
        params.update({"affiliation": "owner,collaborator", "sort": "pushed", "direction": "desc"})
    else:
        params.update({"type": "all", "sort": "pushed", "direction": "desc"})
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            response = await client.get(
                cfg["repos_url"], params=params,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise GitProviderError(f"repository listing unreachable ({type(exc).__name__})") from exc
    try:
        payload = response.json()
    except ValueError:
        raise GitProviderError(f"repository listing failed: HTTP {response.status_code}") from None
    if response.status_code >= 400:
        detail = payload.get("error") or payload.get("message") if isinstance(payload, dict) else ""
        raise GitProviderError(f"repository listing failed: {str(detail)[:200] or f'HTTP {response.status_code}'}")
    items = payload if isinstance(payload, list) else (payload.get("items") or [] if isinstance(payload, dict) else [])
    repos: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        full_name = item.get("full_name") or item.get("human_full_name") or ""
        if not full_name:
            continue
        repos.append({
            "name": str(full_name),
            "private": bool(item.get("private")),
            "default_branch": str(item.get("default_branch") or "master"),
            "updated_at": str(item.get("updated_at") or item.get("pushed_at") or ""),
            "url": str(item.get("html_url") or ""),
            "description": str(item.get("description") or "")[:200],
        })
    return repos


# --- token encryption (stdlib-only, see module docstring) -------------------


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _record_keys(salt: bytes) -> tuple[bytes, bytes]:
    secret = (settings.oauth_encryption_key or settings.auth_secret).encode()
    enc_key = hmac.new(secret, b"interviewos:git-token:v1:enc:" + salt, hashlib.sha256).digest()
    mac_key = hmac.new(secret, b"interviewos:git-token:v1:mac:" + salt, hashlib.sha256).digest()
    return enc_key, mac_key


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return ""
    salt = os.urandom(16)
    nonce = os.urandom(16)
    enc_key, mac_key = _record_keys(salt)
    ciphertext = bytes(a ^ b for a, b in zip(plaintext.encode(), _keystream(enc_key, nonce, len(plaintext.encode()))))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
    return "$".join([_TOKEN_SCHEME, _b64e(salt), _b64e(nonce), _b64e(ciphertext), _b64e(tag)])


def decrypt_token(blob: str) -> str:
    parts = blob.split("$")
    if len(parts) != 5 or parts[0] != _TOKEN_SCHEME:
        raise ValueError("unsupported token encoding")
    try:
        salt, nonce, ciphertext, tag = (_b64d(part) for part in parts[1:])
    except (ValueError, TypeError) as exc:
        raise ValueError("malformed token encoding") from exc
    enc_key, mac_key = _record_keys(salt)
    expected_tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(expected_tag, tag):
        raise ValueError("token integrity check failed")
    return bytes(a ^ b for a, b in zip(ciphertext, _keystream(enc_key, nonce, len(ciphertext)))).decode()
