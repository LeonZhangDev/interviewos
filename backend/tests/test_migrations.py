"""Migration parity: Alembic head must produce the same schema as the
SQLAlchemy models. Catches the "column in model, missing in migration" class
of drift (e.g. a user_id added to a model without a migration).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from app.config import settings
from app.db import Base

import app.models  # noqa: F401  (registers all tables on Base.metadata)


def _migrated_db_path() -> Path:
    return Path(settings.database_url.removeprefix("sqlite+aiosqlite:///"))


def _schema(path: Path) -> dict[str, list[tuple[str, str]]]:
    conn = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
            )
        ]
        return {
            table: [(row[1], row[2]) for row in conn.execute(f"PRAGMA table_info({table})")]
            for table in sorted(tables)
        }
    finally:
        conn.close()


def test_alembic_head_matches_models(tmp_path: Path, migrated_database) -> None:
    metadata_db = tmp_path / "metadata.db"
    sync_engine = create_engine(f"sqlite:///{metadata_db}")
    try:
        Base.metadata.create_all(sync_engine)
    finally:
        sync_engine.dispose()

    migrated = _schema(_migrated_db_path())
    from_models = _schema(metadata_db)

    missing_tables = sorted(set(from_models) - set(migrated))
    extra_tables = sorted(set(migrated) - set(from_models))
    assert not missing_tables, f"Tables missing from migrations: {missing_tables}"
    assert not extra_tables, f"Tables created by migrations but absent from models: {extra_tables}"

    for table in from_models:
        migrated_columns = dict(migrated[table])
        for column, col_type in from_models[table]:
            assert column in migrated_columns, (
                f"models declare {table}.{column} ({col_type}) but migrations do not create it"
            )
            assert migrated_columns[column] == col_type, (
                f"{table}.{column}: model type {col_type} != migrated type {migrated_columns[column]}"
            )


def test_ownership_columns_present(migrated_database) -> None:
    expected = {
        "answer_versions",
        "mastery",
        "interview_sessions",
        "interview_turns",
        "interview_reports",
        "code_explanation_attempts",
        "coding_submissions",
        "coding_wrongbook",
        "repositories",
    }
    conn = sqlite3.connect(_migrated_db_path())
    try:
        for table in expected:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            assert "user_id" in columns, f"{table}.user_id missing after migrations"
        repo_columns = {row[1] for row in conn.execute("PRAGMA table_info(repositories)")}
        assert "is_public" in repo_columns
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert "tokens_valid_after" in user_columns
        refresh_columns = {row[1] for row in conn.execute("PRAGMA table_info(refresh_tokens)")}
        assert {"user_id", "token_hash", "expires_at", "revoked_at"} <= refresh_columns
    finally:
        conn.close()
