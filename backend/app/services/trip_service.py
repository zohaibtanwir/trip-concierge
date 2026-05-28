"""Trip persistence — thin layer between routes and the ORM."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.block import Block
from app.models.day import Day
from app.models.source import Source
from app.models.trip import Trip
from app.schemas.trip import TripCreate


def create_trip(db: Session, payload: TripCreate, *, user_id: uuid.UUID) -> Trip:
    """Create a Trip row owned by the given user_id.

    Slice 3.2 separated user_id from the request body — it now comes
    from the JWT subject via the route's auth dependency, not from
    untrusted input.
    """
    trip = Trip(user_id=user_id, **payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def get_trip(db: Session, trip_id: uuid.UUID) -> Trip | None:
    return db.get(Trip, trip_id)


def persist_regenerated_day(
    db: Session,
    *,
    trip_id: uuid.UUID,
    day_number: int,
    blocks: list[dict[str, Any]],
) -> None:
    """Replace a single Day's blocks with new ones. Slice 3.3 commit 4.

    Surgical update — other days for this trip are untouched. Locked-block
    handling is the worker's responsibility (splice locked blocks into the
    input list before calling this function); this layer writes exactly
    what it receives.

    Raises ValueError if the trip has no Day with the given day_number —
    that's an invariant break the worker shouldn't have triggered, so
    failing loudly here surfaces it instead of silently creating orphan
    blocks under a nonexistent day.
    """
    day = db.execute(
        select(Day).where(Day.trip_id == trip_id, Day.day_number == day_number)
    ).scalar_one_or_none()
    if day is None:
        raise ValueError(f"trip {trip_id} has no day {day_number}")

    # Drop existing blocks; sources cascade via ondelete=CASCADE.
    db.execute(delete(Block).where(Block.day_id == day.id))
    db.flush()

    for block_dict in blocks:
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
        db.flush()
        for url in block_dict.get("source_urls") or []:
            db.add(Source(block_id=block.id, url=str(url)))

    db.commit()


def get_trip_full(db: Session, trip_id: uuid.UUID) -> Trip | None:
    """Fetch a Trip with its days→blocks→sources tree eager-loaded.

    Three queries total via selectinload, regardless of how many days or
    blocks the trip has — avoids the N+1 pattern a naive query would hit.
    Day.blocks and Trip.days carry `order_by` on the relationship, so the
    loaded collections are pre-sorted by the time they reach the route.

    Returns None if the trip doesn't exist.
    """
    stmt = (
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.days).selectinload(Day.blocks).selectinload(Block.sources))
    )
    return db.execute(stmt).scalar_one_or_none()


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
            ...  # audit metadata (approved, revision_log, etc.) — slice 2.5b persists this
                 # to JobRun rows from the arq worker; this function only writes itinerary content.
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
