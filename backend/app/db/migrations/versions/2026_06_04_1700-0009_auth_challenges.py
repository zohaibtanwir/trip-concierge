"""auth_challenges

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-04 17:00:00.000000

Slice 4.1b (0h0) — MCP-side magic-link challenge state.

One row per active magic-link challenge. Owned by backend (not by
pg-adapter), so snake_case columns throughout — the slice-4.1 juo
lesson on camelCase doesn't apply.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_challenges",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mcp_token", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("poll_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("code"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    # Lookup pattern: services.mcp_challenges.create_challenge needs the
    # most-recent pending challenge for an email (debounce + reuse).
    op.create_index(
        "ix_auth_challenges_email_status",
        "auth_challenges",
        ["email", "status"],
    )
    # Used by IP-rate-limit accounting (count last-hour challenges per IP).
    op.create_index(
        "ix_auth_challenges_ip_created",
        "auth_challenges",
        ["ip_address", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_challenges_ip_created", table_name="auth_challenges")
    op.drop_index("ix_auth_challenges_email_status", table_name="auth_challenges")
    op.drop_table("auth_challenges")
