"""HTTP handlers for the trip resource.

Slice 3.2: POST /trips requires `x-tc-token`; user_id is derived from
the JWT subject, never from the request body. The TripCreate schema
no longer carries user_id; defence-in-depth — even if a caller pastes
user_id into the body, Pydantic ignores unknown keys (model_config
extra='ignore' on the schema).

GET /trips/{id} stays open in this slice — locked down by ownership
in a later phase-4 slice when the PWA needs it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.db.session import get_session
from app.models.user import User
from app.schemas.trip import TripCreate, TripFullRead, TripRead
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["trips"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, user: AuthedUser, db: SessionDep) -> TripRead:
    trip = trip_service.create_trip(db, payload, user_id=user.id)
    return TripRead.model_validate(trip)


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: uuid.UUID, db: SessionDep) -> TripRead:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    return TripRead.model_validate(trip)


@router.get("/{trip_id}/full", response_model=TripFullRead)
def get_trip_full(
    trip_id: uuid.UUID,
    _user: AuthedUser,
    db: SessionDep,
) -> TripFullRead:
    """Trip envelope plus the full days→blocks→sources tree.

    Slice 3.3's MCP get_trip tool composes this with /plan/status to render
    the user-facing observability surface (PLANNING / SUCCEEDED / FAILED
    state). plan_status is intentionally NOT returned here — this endpoint
    stays a pure read with no Redis dependency.

    Auth-protected because the response leaks the entire itinerary; the
    `_user` arg is unused inside the handler today (no ownership check
    until Phase 4), but the dependency declaration is what enforces the
    gate.
    """
    trip = trip_service.get_trip_full(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    return TripFullRead.model_validate(trip)
