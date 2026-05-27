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
