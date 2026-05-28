"""Pydantic read schemas for the Day → Block → Source hierarchy.

Used by GET /trips/{id}/full to render the full itinerary tree.
`from_attributes=True` lets FastAPI serialize directly from SQLAlchemy
instances; no manual dict-building in the route. Pre-sorted by the
relationship `order_by` declarations on the models.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    source_type: str
    excerpt: str
    confidence_score: Decimal | None


class BlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order: int
    type: str
    venue_name: str
    lat: Decimal | None
    lng: Decimal | None
    start_time: str | None
    duration_minutes: int
    est_cost: Decimal | None
    currency: str
    locked: bool
    notes: str
    sources: list[SourceRead] = []


class DayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day_number: int
    date: date | None
    summary: str
    blocks: list[BlockRead] = []
