"""v0.8 P1: knowledge prerequisite graph.

Two shared (non-user-owned) tables:

- knowledge_nodes: one row per knowledge point; `chain` matches the seeded
  Mastery topic it belongs to (e.g. "Python / asyncio").
- prerequisite_edges: directed "learn from before to" edges, including a few
  cross-chain dependencies.

Seed data is inserted idempotently by app startup (same pattern as the
question bank), so this migration only creates the schema.

Revision ID: 0005_v08_prerequisites
Revises: 0004_v08_fsrs
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_v08_prerequisites"
down_revision: Union[str, None] = "0004_v08_fsrs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("chain", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_knowledge_node_slug"),
    )
    op.create_index(op.f("ix_knowledge_nodes_chain"), "knowledge_nodes", ["chain"])
    op.create_table(
        "prerequisite_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_slug", sa.String(length=120), nullable=False),
        sa.Column("to_slug", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_slug", "to_slug", name="uq_prerequisite_edge"),
    )
    op.create_index(op.f("ix_prerequisite_edges_from_slug"), "prerequisite_edges", ["from_slug"])
    op.create_index(op.f("ix_prerequisite_edges_to_slug"), "prerequisite_edges", ["to_slug"])


def downgrade() -> None:
    op.drop_index(op.f("ix_prerequisite_edges_to_slug"), table_name="prerequisite_edges")
    op.drop_index(op.f("ix_prerequisite_edges_from_slug"), table_name="prerequisite_edges")
    op.drop_table("prerequisite_edges")
    op.drop_index(op.f("ix_knowledge_nodes_chain"), table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
