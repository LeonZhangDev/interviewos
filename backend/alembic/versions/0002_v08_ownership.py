"""v0.8 P0: full user ownership for private workspace data.

- Adds a nullable user_id FK (users.id, ON DELETE CASCADE) to every private table.
- Replaces global unique constraints with per-user ones
  (mastery topic, coding wrong-book entry, repository source).
- Adds repositories.is_public so the public portfolio only exposes
  repos the owner explicitly makes public.
- Backfills legacy single-user data: when exactly one user exists, all
  legacy rows are assigned to that user. With zero users the rows stay
  orphaned (user_id NULL, invisible to everyone) and are claimed by the
  first account created afterwards. With two or more users the rows were
  written by an ambiguous shared workbench, so they stay unassigned
  rather than leaking one user's answers to another.

Downgrade restores the v0.7 global constraints; it fails if the per-user
data already contains duplicates under the old global rules.

Revision ID: 0002_v08_ownership
Revises: 0001_v07_baseline
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_v08_ownership"
down_revision: Union[str, None] = "0001_v07_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRIVATE_TABLES = (
    "answer_versions",
    "mastery",
    "interview_sessions",
    "code_explanation_attempts",
    "coding_submissions",
    "coding_wrongbook",
    "repositories",
)

SESSION_CHILD_TABLES = (
    "interview_turns",
    "interview_reports",
)


def upgrade() -> None:
    for table in (*PRIVATE_TABLES, *SESSION_CHILD_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")
            batch.create_index(f"ix_{table}_user_id", ["user_id"], unique=False)

    with op.batch_alter_table("repositories") as batch:
        batch.add_column(sa.Column("is_public", sa.Integer(), nullable=False, server_default="0"))

    with op.batch_alter_table("mastery") as batch:
        batch.drop_constraint("uq_mastery_topic", type_="unique")
        batch.create_unique_constraint("uq_mastery_user_topic", ["user_id", "topic"])
    with op.batch_alter_table("coding_wrongbook") as batch:
        batch.drop_constraint("uq_coding_wrong_challenge", type_="unique")
        batch.create_unique_constraint("uq_coding_wrong_user_challenge", ["user_id", "challenge_id"])
    with op.batch_alter_table("repositories") as batch:
        batch.drop_constraint("uq_repository_source", type_="unique")
        batch.create_unique_constraint("uq_repository_user_source", ["user_id", "provider", "url", "branch"])

    _backfill_legacy_owner()


def _backfill_legacy_owner() -> None:
    bind = op.get_bind()
    user_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM users ORDER BY id")).fetchall()]
    if len(user_ids) != 1:
        return
    owner = user_ids[0]
    for table in PRIVATE_TABLES:
        bind.execute(sa.text(f"UPDATE {table} SET user_id = :owner WHERE user_id IS NULL"), {"owner": owner})
    for table in SESSION_CHILD_TABLES:
        bind.execute(
            sa.text(
                f"UPDATE {table} SET user_id = :owner "
                "WHERE user_id IS NULL AND session_id IN "
                "(SELECT id FROM interview_sessions WHERE user_id = :owner)"
            ),
            {"owner": owner},
        )


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_constraint("uq_repository_user_source", type_="unique")
        batch.create_unique_constraint("uq_repository_source", ["provider", "url", "branch"])
    with op.batch_alter_table("coding_wrongbook") as batch:
        batch.drop_constraint("uq_coding_wrong_user_challenge", type_="unique")
        batch.create_unique_constraint("uq_coding_wrong_challenge", ["challenge_id"])
    with op.batch_alter_table("mastery") as batch:
        batch.drop_constraint("uq_mastery_user_topic", type_="unique")
        batch.create_unique_constraint("uq_mastery_topic", ["topic"])
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("is_public")
    for table in (*PRIVATE_TABLES, *SESSION_CHILD_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_user_id")
            batch.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
            batch.drop_column("user_id")
