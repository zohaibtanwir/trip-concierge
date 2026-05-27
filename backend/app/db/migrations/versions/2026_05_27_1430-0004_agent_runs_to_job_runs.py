"""agent_runs to job_runs

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-27 14:30:50.007934

Slice 2.5b architecture decision: don't write per-agent rows on partial
failure. One row per job is enough observability for v1.0 (see
agents/src/trip_agents/worker.py and the JobRun model docstring for the
reasoning).

`agent_runs` (slice 2.4) is dropped and replaced by `job_runs`. No data
migration — agent_runs has zero production rows.

Migration is round-trippable: downgrade() recreates the original
agent_runs schema from migration 0003, so a rollback to 0003 lands in the
same state we left it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_agent_runs_trip_id", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.create_table(
        "job_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "agent_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_cost", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("total_duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_job_runs_trip_id", "job_runs", ["trip_id"], unique=False)
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_runs_job_id", table_name="job_runs")
    op.drop_index("ix_job_runs_trip_id", table_name="job_runs")
    op.drop_table("job_runs")

    # Recreate agent_runs in its slice-2.4 (migration 0003) form so a
    # downgrade to revision 0003 lands in the same schema we left.
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_trip_id", "agent_runs", ["trip_id"], unique=False)
