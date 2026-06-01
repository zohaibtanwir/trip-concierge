"""auth_js_tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-01 16:30:00.000000

Slice 4.1 (mvs) — Auth.js v5 schema for PWA-side sign-in.

Adds:
- users."emailVerified" (TIMESTAMPTZ NULL) — Auth.js sets on first verified login
- users.image (TEXT NULL)                  — Auth.js populates from OAuth profile
- accounts table                           — OAuth + email-provider linkage rows
- verification_token table                 — magic-link tokens (consumed once)

NO sessions table — slice 4.1 chose JWT session strategy. Session lives in
an encrypted cookie owned by Auth.js; no replica-shared session state needed
for v1.0a scale. pg-adapter's createSession/updateSession/etc methods are
never called under JWT strategy.

Column naming — IMPORTANT. The @auth/pg-adapter package (v1.11.2) hardcodes
its SQL with EXACT column and table names. It does NOT accept a column-
aliasing options object. Schema must match pg-adapter's expected shape
verbatim. Caught at PR #32 review pre-merge (see experiments/01-langfuse.md
"Concern #1" observation).

  Column / table          Why quoted?
  ----------------------  ------------------------------------------------
  users."emailVerified"   pg-adapter line 64-66 quotes "emailVerified"
  accounts."userId"       pg-adapter line 94, 133, 148 quotes "userId"
  accounts."providerAccountId"   pg-adapter line 98, 136, 151 quotes it
  verification_token      pg-adapter line 41 hardcodes table name (singular)

PostgreSQL treats `"camelCase"` as case-sensitive, so we MUST use the
quoted form in both the migration and any backend code that references
these columns. Snake_case columns the adapter DOES use (access_token,
refresh_token, expires_at, etc.) are referenced unquoted by pg-adapter
and work as ordinary identifiers.

Two-writers note: pg-adapter (running in the Next.js server) is the
authoritative writer for accounts and verification_token. The Python
backend only READS users (and writes via SQLAlchemy on the existing
flows). Tests in backend/tests/test_auth_mint_route.py insert directly
into accounts via raw SQL to simulate the pg-adapter writes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Quoted identifiers (sa.Column passes the literal name to PG; PG
    # preserves case when the SQL emitted by SQLAlchemy quotes the name,
    # which it does for camelCase identifiers automatically).
    op.add_column(
        "users",
        sa.Column("emailVerified", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("image", sa.Text(), nullable=True),
    )

    op.create_table(
        "accounts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("userId", sa.UUID(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("providerAccountId", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.BigInteger(), nullable=True),
        sa.Column("token_type", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("session_state", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["userId"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "providerAccountId", name="uq_accounts_provider_account"),
    )
    op.create_index(
        op.f("ix_accounts_userId"),
        "accounts",
        ["userId"],
        unique=False,
    )

    # Singular table name — pg-adapter hardcodes `verification_token`.
    op.create_table(
        "verification_token",
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("identifier", "token"),
    )


def downgrade() -> None:
    op.drop_table("verification_token")
    op.drop_index(op.f("ix_accounts_userId"), table_name="accounts")
    op.drop_table("accounts")
    op.drop_column("users", "image")
    op.drop_column("users", "emailVerified")
