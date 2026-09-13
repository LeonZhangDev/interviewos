"""v0.8 P0: refresh token lifecycle.

- refresh_tokens stores SHA-256 hashes of opaque refresh tokens with
  expiry and revocation timestamps; rotation happens on every refresh.
- users.tokens_valid_after is an access-token revocation watermark:
  logout and password change bump it, invalidating outstanding access
  tokens issued before that moment.

Revision ID: 0003_v08_auth_lifecycle
Revises: 0002_v08_ownership
Create Date: 2026-09-06

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_v08_auth_lifecycle"
down_revision: Union[str, None] = "0002_v08_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("tokens_valid_after", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'"))
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("tokens_valid_after")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
