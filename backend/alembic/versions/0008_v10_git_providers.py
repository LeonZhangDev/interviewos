"""v1.0 P0: Git provider integrations (GitHub / Gitee OAuth).

- git_connections: per-user authorized provider account. The provider access
  token is stored encrypted (app/git_oauth.py stdlib HMAC-CTR + EtM scheme,
  master key from OAUTH_ENCRYPTION_KEY / AUTH_SECRET); one row per
  (user, provider).
- oauth_states: single-use CSRF state rows binding an authorization request
  to the user who started it (10-minute TTL, consumed on callback).
- repositories.is_private: provider-side visibility of the source repository,
  display metadata only — portfolio exposure stays governed by is_public.

Revision ID: 0008_v10_git_providers
Revises: 0007_v09_advanced_interview
Create Date: 2026-09-09

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_v10_git_providers"
down_revision: Union[str, None] = "0007_v09_advanced_interview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "git_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_login", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("provider_user_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("scopes", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_git_connection_user_provider"),
    )
    op.create_index(op.f("ix_git_connections_user_id"), "git_connections", ["user_id"])
    op.create_index(op.f("ix_git_connections_provider"), "git_connections", ["provider"])

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_oauth_states_state"), "oauth_states", ["state"], unique=True)
    op.create_index(op.f("ix_oauth_states_user_id"), "oauth_states", ["user_id"])

    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("is_private", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("is_private")
    op.drop_index(op.f("ix_oauth_states_user_id"), table_name="oauth_states")
    op.drop_index(op.f("ix_oauth_states_state"), table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index(op.f("ix_git_connections_provider"), table_name="git_connections")
    op.drop_index(op.f("ix_git_connections_user_id"), table_name="git_connections")
    op.drop_table("git_connections")
