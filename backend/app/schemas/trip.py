"""Pydantic schemas for the trip resource — request bodies and responses.

Slice 3.2 dropped user_id from TripCreate; it's derived server-side
from the JWT subject. `extra="ignore"` makes the field disappear from
the body silently if a client tries to send it — defence in depth.
TripRead still surfaces user_id (it's set by the route handler from
the auth dependency and persisted to the row).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.day import DayRead


class TripCreate(BaseModel):
    """POST /trips body. `user_id` is derived from the JWT subject by
    the route handler — it is NOT accepted in the body.
    """

    model_config = ConfigDict(extra="ignore")

    destination: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    group_size: int = Field(default=1, ge=1)
    budget_total: Decimal | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    constraints: dict[str, Any] = Field(default_factory=dict)
    pace: str = Field(default="balanced")


class TripRead(BaseModel):
    """GET /trips/{id} response and POST /trips response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    destination: str
    start_date: date | None
    end_date: date | None
    group_size: int
    budget_total: Decimal | None
    currency: str
    constraints: dict[str, Any]
    pace: str
    created_at: datetime
    updated_at: datetime


class TripFullRead(TripRead):
    """GET /trips/{id}/full — TripRead plus the days→blocks→sources tree.

    Used by the MCP get_trip tool (slice 3.3). plan_status is intentionally
    NOT included here; the MCP tool composes /full with /plan/status itself
    (two HTTP calls, matching the create_trip pattern from 3.2). Keeps this
    endpoint a pure read with no Redis dependency.
    """

    days: list[DayRead] = []


class TripListItem(BaseModel):
    """One row in the trip list (GET /trips).

    Slimmer than TripRead: drops user_id (caller already knows whose list
    this is), constraints (not rendered on list cards), group_size + pace
    (detail-page concerns), status (the dead-column-since-1.x). Adds the
    derived `state` composed via Postgres + Redis dual-read per slice 4.2.

    state ∈ {'succeeded', 'failed', 'planning', 'no_job'}:
      - 'succeeded' / 'failed' from latest plan-kind JobRun (Postgres)
      - 'planning' from Redis active_job key (queued/running phase)
      - 'no_job' otherwise

    See trip_service.list_trips_for_user for the composition rule.
    Long-term elimination of the dual-read tracked as trip-concierge-hia.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    destination: str
    start_date: date | None
    end_date: date | None
    currency: str
    budget_total: Decimal | None
    state: str
    created_at: datetime


class TripListResponse(BaseModel):
    """GET /trips response envelope.

    Wrapping the array gives room to add metadata (next_cursor, total) in
    the future without a breaking schema change.
    """

    items: list[TripListItem]
