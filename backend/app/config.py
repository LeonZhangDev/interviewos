from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://interviewos:interviewos@db:5432/interviewos"
    redis_url: str = "redis://redis:6379/0"
    runner_url: str = "http://runner:8001"
    cors_origins: str = "http://localhost:5173"

    # Any OpenAI-compatible endpoint can be used here: OpenAI, DeepSeek, vLLM, etc.
    # Leave blank to use InterviewOS' deterministic offline fallback.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    auth_secret: str = "change-me-in-production-interviewos"
    # Access tokens are short-lived; the frontend silently refreshes them.
    auth_token_minutes: int = 60
    auth_refresh_days: int = 14
    recordings_dir: str = "/data/recordings"

    # v1.0 Git provider OAuth (GitHub / Gitee). Leave the client id/secret
    # blank to keep the anonymous public-repository sync path only; nothing
    # else degrades when OAuth is unconfigured.
    github_client_id: str = ""
    github_client_secret: str = ""
    gitee_client_id: str = ""
    gitee_client_secret: str = ""
    # Master secret used to encrypt provider access tokens at rest
    # (app/git_oauth.py). Rotating it invalidates every stored token — users
    # must disconnect and re-authorize. Falls back to AUTH_SECRET so local
    # development works without an extra variable.
    oauth_encryption_key: str = ""
    # Public frontend origin the providers redirect back to
    # (<base>/oauth/callback must be registered as the OAuth callback URL).
    oauth_redirect_base: str = "http://localhost:5173"

    # v1.0 P1 Playgrounds. The backend mirrors the runner's sandbox limits to
    # reject oversized input before proxying; the runner re-validates with the
    # same values (app/playground.py keeps both sides in sync, parity-tested).
    playground_sql_max_chars: int = 8000
    playground_redis_max_chars: int = 500
    playground_fastapi_max_chars: int = 12000
    playground_session_ttl_hours: int = 24

    # v1.0 Observability. LOG_FORMAT json (default, one object per line) or
    # text (human-readable local development). SENTRY_DSN is a no-op when
    # blank — sentry-sdk stays an optional extra, never a hard dependency.
    log_format: str = "json"
    log_level: str = "INFO"
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
