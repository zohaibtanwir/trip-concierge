"""JobRun model — one row per crew-planning job (succeeded / failed / cancelled).

Slice 2.5b replaced the slice-2.4 AgentRun model. The decision: don't write
per-agent rows for partial failures in v1.0; getting per-agent state on
failure requires reconstructing from Langfuse or hooking step_callback
mid-failure, and the partial-write complexity isn't worth it. One row per
job is enough observability for cost analysis + the "which agent failed?"
question via the agent_summary JSONB column.

Fields NOT stored here on purpose:
- The TripRunRequest input — recoverable from the `trips` row.
- The AuditedPlan output — the canonical record is the days/blocks/sources
  rows. Re-storing it would duplicate data.

Per-agent rows are a v2.0 question if we ever need them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # arq's job_id is hex (not a UUID). Unique because each enqueue produces
    # one new id; indexed because the status endpoint looks up by it.
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Final state only. Hot state (queued/running) lives in Redis.
    # Worker writes this row on terminal events: succeeded | failed | cancelled.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-agent event log captured by CrewAI's step_callback. Best-effort —
    # may be partial on failure. See worker._make_step_callback.
    agent_summary: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )

    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        server_default="0",
    )
    total_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
