"""v1.0 P2: Portfolio CMS.

- portfolio_profiles: one row per user, the configurable public portfolio
  (display name, headline, summary, skills, resume/social links) with
  is_published as the master visibility switch. While off, the public
  portfolio endpoint keeps serving the legacy static view; once on, it serves
  exactly the configured fields plus the user's portfolio projects.
- portfolio_projects: user-authored project entries (title, subtitle,
  description, architecture notes, engineering decisions, tech tags, demo
  link) with per-entry visibility and ordering. Each entry may bind one of the
  user's synced repositories; the public view only reveals the bound
  repository when that repository is itself marked public.

Revision ID: 0010_v10_p2_portfolio_cms
Revises: 0009_v10_p1_playgrounds
Create Date: 2026-09-09

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_v10_p2_portfolio_cms"
down_revision: Union[str, None] = "0009_v10_p1_playgrounds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("headline", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("skills_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_published", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resume_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("social_links_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_portfolio_profile_user"),
    )
    op.create_index(op.f("ix_portfolio_profiles_user_id"), "portfolio_profiles", ["user_id"], unique=True)

    op.create_table(
        "portfolio_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("architecture", sa.Text(), nullable=False, server_default=""),
        sa.Column("decisions", sa.Text(), nullable=False, server_default=""),
        sa.Column("tech_tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("link", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_visible", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_projects_user_id"), "portfolio_projects", ["user_id"])
    op.create_index(op.f("ix_portfolio_projects_repository_id"), "portfolio_projects", ["repository_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_portfolio_projects_repository_id"), table_name="portfolio_projects")
    op.drop_index(op.f("ix_portfolio_projects_user_id"), table_name="portfolio_projects")
    op.drop_table("portfolio_projects")
    op.drop_index(op.f("ix_portfolio_profiles_user_id"), table_name="portfolio_profiles")
    op.drop_table("portfolio_profiles")
