"""v1.0 P1: Playground sandbox sessions.

- playground_sessions: one row per user sandbox session (kind sql / redis).
  The unguessable session key is what the runner derives the isolated
  PostgreSQL schema name and Redis database index from; the table itself
  stores no sandbox data (contents live only in the runner's sandbox
  services) and rows are lazily deleted once expired.

Revision ID: 0009_v10_p1_playgrounds
Revises: 0008_v10_git_providers
Create Date: 2026-09-09

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_v10_p1_playgrounds"
down_revision: Union[str, None] = "0008_v10_git_providers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playground_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_key", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key", name="uq_playground_session_key"),
    )
    op.create_index(op.f("ix_playground_sessions_session_key"), "playground_sessions", ["session_key"], unique=True)
    op.create_index(op.f("ix_playground_sessions_user_id"), "playground_sessions", ["user_id"])
    op.create_index(op.f("ix_playground_sessions_kind"), "playground_sessions", ["kind"])


def downgrade() -> None:
    op.drop_index(op.f("ix_playground_sessions_kind"), table_name="playground_sessions")
    op.drop_index(op.f("ix_playground_sessions_user_id"), table_name="playground_sessions")
    op.drop_index(op.f("ix_playground_sessions_session_key"), table_name="playground_sessions")
    op.drop_table("playground_sessions")
