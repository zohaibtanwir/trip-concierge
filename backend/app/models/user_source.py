"""UserSource model — trip-anchored user-pasted research corpus.

Slice 3.4b commit 1. Parallel to but separate from the block-anchored
Source model:

- `Source` (slice 2.4): citation FK to blocks. Block-citation invariant
  per PRD F6 — every venue/meal Block has ≥1 Source.
- `UserSource` (slice 3.4b): FK to trips. Research the user pasted or
  shared via add_source; the Researcher consumes it as a corpus at
  refine time (via the existing {user_sources} prompt-template
  variable in slice-2.4 tasks.py).

The two-table split avoided an M×N anti-pattern: forcing user-pasted
research into the Block-anchored sources table would have required
either a synthetic "trip-level virtual Block" anti-pattern or
duplicate rows across every current Block. File-tree session decision
captured in BUILD_PLAN.md Slice 3.4b.

v1.0a (this commit) ships URL fetch + raw-text storage only. No
pgvector embedding column — deferred to ticket trip-concierge-pcm
(P2; blocked until a consumer exists: user_sources_search_tool for
the Researcher).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSource(Base):
    __tablename__ = "user_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL when the user pasted raw text rather than sharing a URL.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The consumable. HTML→text for url_fetched; verbatim for user_text.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # url_fetched | user_text. String rather than Enum so the migration
    # stays trivial and future content_types (e.g. youtube_transcript)
    # don't need an enum-extension migration.
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
