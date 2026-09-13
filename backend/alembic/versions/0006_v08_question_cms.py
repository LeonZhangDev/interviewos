"""v0.8 P2: question CMS.

Questions stay shared content (the private boundary lives in answers/mastery),
but gain CMS bookkeeping columns:

- archived: soft-delete flag; archived questions disappear from the default
  question list and unified search until restored.
- tags: pipe-separated tag list, same storage convention as coding challenges.
- created_by: the user who created/edited the question (NULL for seed rows).
- updated_at: last edit timestamp.

Revision ID: 0006_v08_question_cms
Revises: 0005_v08_prerequisites
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_v08_question_cms"
down_revision: Union[str, None] = "0005_v08_prerequisites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("archived", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("tags", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_questions_created_by_users", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_questions_archived"), "questions", ["archived"])


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_archived"), table_name="questions")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("created_by")
        batch.drop_column("tags")
        batch.drop_column("archived")
