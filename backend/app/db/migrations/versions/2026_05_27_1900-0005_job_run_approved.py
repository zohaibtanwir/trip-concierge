"""job_run.approved

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27 19:00:00.000000

Slice 2.5c adds `approved BOOLEAN NULL` to job_runs. Surfaces the auditor's
outcome on the status endpoint without re-reading days/blocks. Nullable
because it only carries meaning for status=succeeded; failed and cancelled
rows leave it null.

No data backfill — job_runs has zero production rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("approved", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_runs", "approved")
