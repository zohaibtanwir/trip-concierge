"""job_run.kind

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-28 00:01:00.000000

Slice 3.3 adds `kind VARCHAR(20) NOT NULL DEFAULT 'plan'` to job_runs.
Discriminates between create_trip's enqueued job ('plan'), refine_trip's
hierarchical job ('refine'), and regenerate_day's day-scoped job ('regen').

Server-default 'plan' backfills existing rows and keeps pre-3.3 call
sites (worker.plan_trip writes JobRun without specifying kind) correct
without code changes. Subsequent commits in slice 3.3 wire the refine
and regen writers to set kind explicitly.

No data migration needed — job_runs has zero production rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="plan"),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "kind")
