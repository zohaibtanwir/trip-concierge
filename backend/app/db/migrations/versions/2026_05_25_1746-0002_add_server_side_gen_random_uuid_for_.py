"""add server-side gen_random_uuid for users.id and trips.id

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25 17:46:23.878110

Originally the UUID primary keys had only a Python-side default
(uuid.uuid4 on the SQLAlchemy model), which doesn't apply to raw
SQL inserts. Adding a Postgres-side default via gen_random_uuid()
keeps the schema robust against backfill scripts, seed data, manual
recovery, and anything else that bypasses the ORM.

gen_random_uuid() is built into Postgres 13+ — no extension needed.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "id",
        server_default=sa.text("gen_random_uuid()"),
    )
    op.alter_column(
        "trips",
        "id",
        server_default=sa.text("gen_random_uuid()"),
    )


def downgrade() -> None:
    op.alter_column("users", "id", server_default=None)
    op.alter_column("trips", "id", server_default=None)
