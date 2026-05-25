"""Trip persistence — thin layer between routes and the ORM."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

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
