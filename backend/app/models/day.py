"""Day model — one calendar day within a Trip's itinerary."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.block import Block


class Day(Base):
    __tablename__ = "days"

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
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationship for selectinload-based tree fetch in GET /trips/{id}/full.
    # order_by on the relationship means consumers (service.get_trip_full,
    # Pydantic schema serialization) get pre-sorted Blocks without needing
    # to re-sort.
    blocks: Mapped[list[Block]] = relationship(
        "Block",
        order_by="Block.order",
        cascade="all, delete-orphan",
        lazy="select",
    )
