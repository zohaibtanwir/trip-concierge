"""Trip persistence — thin layer between routes and the ORM."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.source import Source
from app.models.trip import Trip
from app.schemas.trip import TripCreate


def create_trip(db: Session, payload: TripCreate) -> Trip:
    trip = Trip(**payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def get_trip(db: Session, trip_id: uuid.UUID) -> Trip | None:
    return db.get(Trip, trip_id)


def persist_audited_plan(
    db: Session,
    trip_id: uuid.UUID,
    audited: dict[str, Any],
) -> None:
    """Replace a Trip's Days/Blocks/Sources with rows from an AuditedPlan dict.

    Destructive-overwrite by design: the trip's existing Days are deleted
    (CASCADE removes Blocks and Sources), then new rows are inserted from
    `audited["days"]`. Intended for `POST /trips/{id}/plan` (slice 2.5) and
    full-trip regen tools (Phase 3). Per-block edits use a narrower path.

    Audited shape (from agents.schemas.AuditedPlan.model_dump()):
        {
            "days": [
                {
                    "day_number": int,
                    "date": str | None,
                    "summary": str,
                    "blocks": [
                        {
                            "order": int,
                            "type": "venue"|"transit"|"meal"|"rest",
                            "venue_name": str,
                            "start_time": str | None,
                            "duration_minutes": int,
                            "est_cost": float | None,
                            "currency": str,
                            "source_urls": [str, ...],
                            ...  # extra fields tolerated and ignored
                        },
                    ],
                },
            ],
            ...  # audit metadata (approved, revision_log, etc.) — slice 2.5 persists this
                 # to AgentRun rows; this function only writes itinerary content.
        }
    """
    # Wipe existing Days for this trip; CASCADE handles Blocks + Sources.
    db.execute(delete(Day).where(Day.trip_id == trip_id))

    for day_dict in audited.get("days") or []:
        day = Day(
            trip_id=trip_id,
            day_number=int(day_dict["day_number"]),
            date=_parse_date(day_dict.get("date")),
            summary=str(day_dict.get("summary") or ""),
        )
        db.add(day)
        db.flush()  # populate day.id for block FK

        for block_dict in day_dict.get("blocks") or []:
            block = Block(
                day_id=day.id,
                order=int(block_dict["order"]),
                type=str(block_dict["type"]),
                venue_name=str(block_dict["venue_name"]),
                start_time=block_dict.get("start_time"),
                duration_minutes=int(block_dict.get("duration_minutes") or 0),
                est_cost=_to_decimal(block_dict.get("est_cost")),
                currency=str(block_dict.get("currency") or "USD"),
                notes=str(block_dict.get("notes") or ""),
            )
            db.add(block)
            db.flush()  # populate block.id for source FK

            for url in block_dict.get("source_urls") or []:
                db.add(Source(block_id=block.id, url=str(url)))

    db.commit()


def _parse_date(raw: Any) -> date_type | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date_type):
        return raw
    return date_type.fromisoformat(str(raw))


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    return Decimal(str(raw))
