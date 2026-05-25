"""HTTP handlers for the trip resource."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.trip import TripCreate, TripRead
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["trips"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, db: SessionDep) -> TripRead:
    trip = trip_service.create_trip(db, payload)
    return TripRead.model_validate(trip)


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: uuid.UUID, db: SessionDep) -> TripRead:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    return TripRead.model_validate(trip)
