"""v0.9: advanced interview (personas / memory / time controller).

- interview_sessions.persona: interviewer persona id (questioning style and
  scoring emphasis only; the factual standard stays identical).
- interview_sessions.module_starts: JSON {module_index: iso_timestamp} set when
  the candidate enters each script module, so the time controller can compare
  actual elapsed time (including thinking time) against module budgets.
- interview_turns.module_index: script index the turn belongs to.
- interview_reports.memory_findings: JSON {findings, summary} with
  deterministic memory findings (contradictions, unanswered, evasions,
  avoided concepts, reused gaps).
- interview_reports.time_execution: JSON {plan_minutes, elapsed_minutes,
  modules, advisory} with planned vs actual time per module.

Revision ID: 0007_v09_advanced_interview
Revises: 0006_v08_question_cms
Create Date: 2026-09-09

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_v09_advanced_interview"
down_revision: Union[str, None] = "0006_v08_question_cms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch:
        batch.add_column(sa.Column("persona", sa.String(length=40), nullable=False, server_default="normal"))
        batch.add_column(sa.Column("module_starts", sa.Text(), nullable=False, server_default="{}"))
    with op.batch_alter_table("interview_turns") as batch:
        batch.add_column(sa.Column("module_index", sa.Integer(), nullable=True))
    with op.batch_alter_table("interview_reports") as batch:
        batch.add_column(sa.Column("memory_findings", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("time_execution", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("interview_reports") as batch:
        batch.drop_column("time_execution")
        batch.drop_column("memory_findings")
    with op.batch_alter_table("interview_turns") as batch:
        batch.drop_column("module_index")
    with op.batch_alter_table("interview_sessions") as batch:
        batch.drop_column("module_starts")
        batch.drop_column("persona")
