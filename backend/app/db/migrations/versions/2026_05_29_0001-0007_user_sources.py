"""user_sources

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29 00:01:00.000000

Slice 3.4b commit 1 — creates the trip-anchored user_sources table
backing the add_source MCP tool. Parallel to but separate from the
slice-2.4 block-anchored `sources` table (see app/models/user_source.py
docstring for the M×N-anti-pattern rationale).

v1.0a does NOT include a pgvector embedding column. Embedding is
deferred to ticket trip-concierge-pcm (P2; blocked until consumer
exists). When pcm lands, migration 0008 will add the embedding column;
this migration deliberately ships the table without it so the v1.0a
URL-fetch path can be exercised end-to-end first.

No data migration needed — fresh table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_sources",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_sources_trip_id"),
        "user_sources",
        ["trip_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_sources_trip_id"), table_name="user_sources")
    op.drop_table("user_sources")
