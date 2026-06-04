"""AuthChallenge — MCP-side magic-link challenge state.

Slice 4.1b (0h0). One row per active magic-link challenge. Lifecycle:

  pending  (created at /auth/mcp/challenge, email sent)
    │
    ├──→ redeemed  (user clicked /auth/mcp/redeem, JWT minted)
    │       │
    │       └──→ consumed  (MCP server polled /poll/{code} and pulled JWT;
    │                       one-shot replay protection)
    │
    └──→ expired   (10-min TTL elapsed OR poll_count >= 300)

snake_case columns — this table is owned by the backend (not pg-adapter),
so the slice-4.1 juo lesson doesn't apply here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ChallengeStatus = Literal["pending", "redeemed", "expired", "consumed"]


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    # secrets.token_urlsafe(16) — 22 chars base64url. PK because the code IS
    # the per-challenge identifier; we look it up by URL fragment, not UUID.
    code: Mapped[str] = mapped_column(Text, primary_key=True)

    # Captured at /challenge time from the MCP server's request payload.
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Populated at /redeem time. ON DELETE SET NULL preserves the row for
    # audit even after a user deletes their account.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The minted MCP JWT, populated at /redeem. NULL while pending.
    mcp_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 'pending' | 'redeemed' | 'expired' | 'consumed'. TEXT not enum per Q6 —
    # easier to migrate, no enum-maintenance overhead.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")

    # IP of the MCP-server's /challenge POST. Used for IP-rate-limit lookup.
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    # Lifetime cap: poll_count >= 300 → set status=expired, return 410.
    # Matches RATE_LIMIT_POLL_PER_CODE = "1/2seconds" × 600s lifetime = 300.
    poll_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # created_at + 10 minutes, set by the service at create time.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
