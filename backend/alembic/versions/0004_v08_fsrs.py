"""v0.8 P1: FSRS-4.5 spaced repetition.

- mastery gains the FSRS memory state: stability, difficulty, reps,
  lapses, last_review_at (stability/difficulty of 0 marks a row that has
  not been FSRS-seeded yet).
- review_logs records every review event (manual grade, question answer,
  interview turn, code explanation, coding submission) together with the
  resulting FSRS state, enabling review history and future parameter
  optimization.
- Legacy backfill: rows written by the fixed 1/3/7/14-day scheduler are
  seeded with stability = legacy interval (I(r=0.9, S) = S) and
  difficulty mapped from the 0-100 mastery score (50 -> 5.0, 100 -> 1.0),
  so FSRS continues roughly where the fixed intervals left off.

Revision ID: 0004_v08_fsrs
Revises: 0003_v08_auth_lifecycle
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_v08_fsrs"
down_revision: Union[str, None] = "0003_v08_auth_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("mastery") as batch:
        batch.add_column(sa.Column("stability", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("difficulty", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reps", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_review_at", sa.DateTime(), nullable=True))

    # Every existing row was written by the legacy fixed-interval scheduler.
    # Backfill a plausible last_review_at (due_at - interval) so the row keeps
    # its maturity instead of restarting as a brand-new FSRS card.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "UPDATE mastery SET "
            "stability = MAX(0.1, MIN(365.0, CASE WHEN interval_days > 0 THEN interval_days ELSE 1 END)), "
            "difficulty = MAX(1.0, MIN(10.0, 10.0 - score * 0.1)), "
            "reps = 1, "
            "last_review_at = datetime(due_at, '-' || interval_days || ' days')"
        )
    else:
        # PostgreSQL: MAX/MIN are aggregates only; the scalar two-argument
        # forms are GREATEST/LEAST.
        op.execute(
            "UPDATE mastery SET "
            "stability = GREATEST(0.1, LEAST(365.0, CASE WHEN interval_days > 0 THEN interval_days ELSE 1 END)), "
            "difficulty = GREATEST(1.0, LEAST(10.0, 10.0 - score * 0.1)), "
            "reps = 1, "
            "last_review_at = due_at - make_interval(days => interval_days)"
        )

    op.create_table(
        "review_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mastery_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("retrievability", sa.Float(), nullable=False),
        sa.Column("elapsed_days", sa.Float(), nullable=False),
        sa.Column("scheduled_days", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mastery_id"], ["mastery.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_logs_mastery_id"), "review_logs", ["mastery_id"], unique=False)
    op.create_index(op.f("ix_review_logs_user_id"), "review_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_review_logs_topic"), "review_logs", ["topic"], unique=False)
    op.create_index(op.f("ix_review_logs_reviewed_at"), "review_logs", ["reviewed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_logs_reviewed_at"), table_name="review_logs")
    op.drop_index(op.f("ix_review_logs_topic"), table_name="review_logs")
    op.drop_index(op.f("ix_review_logs_user_id"), table_name="review_logs")
    op.drop_index(op.f("ix_review_logs_mastery_id"), table_name="review_logs")
    op.drop_table("review_logs")
    with op.batch_alter_table("mastery") as batch:
        batch.drop_column("last_review_at")
        batch.drop_column("lapses")
        batch.drop_column("reps")
        batch.drop_column("difficulty")
        batch.drop_column("stability")
