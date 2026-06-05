"""HTTP handlers for the trip resource.

Slice 3.2: POST /trips requires `x-tc-token`; user_id is derived from
the JWT subject, never from the request body. The TripCreate schema
no longer carries user_id; defence-in-depth — even if a caller pastes
user_id into the body, Pydantic ignores unknown keys (model_config
extra='ignore' on the schema).

Slice 4.2 (trip-concierge-2th): closed three deferred-since-slice-2.x
auth holes — added GET /trips (list, owner-filtered), added ownership
checks on GET /trips/{id} + GET /trips/{id}/full (both 403 on cross-
user). Cross-user reads return 403 (not 404): the trip exists, you
just can't see it.

Slice 4.2 tightening: added GET /internal/trips/{tripId}/active-job
(internal_router below). The PWA detail page calls this when
/plan/status returns 404 — distinguishes "worker enqueued but
JobRun not yet written" (UX state: planning) from "no plan attempt
ever made" (UX state: no_job). Without this, a user landing on
the detail page within the ~1-3s enqueue → first-JobRun-write window
would see a blank page. The endpoint uses the same INTERNAL_AUTH_SECRET
pattern as /internal/auth/mint-mcp-token.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.schemas.trip import (
    TripCreate,
    TripFullRead,
    TripListItem,
    TripListResponse,
    TripRead,
)
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["trips"])
internal_router = APIRouter(prefix="/internal/trips", tags=["internal-trips"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


def _internal_secret() -> str:
    """Indirection so tests can patch this without monkey-patching settings.

    Same pattern as app.routes.auth._internal_secret. Each route module
    that uses INTERNAL_AUTH_SECRET keeps its own helper so test patches
    don't have to remember which module wraps which helper.
    """
    return settings.internal_auth_secret


class ActiveJobResponse(BaseModel):
    active: bool


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, user: AuthedUser, db: SessionDep) -> TripRead:
    trip = trip_service.create_trip(db, payload, user_id=user.id)
    return TripRead.model_validate(trip)


@router.get("", response_model=TripListResponse)
async def list_trips(user: AuthedUser, db: SessionDep) -> TripListResponse:
    """List the authenticated user's trips, newest first, capped at 50.

    Each item carries a derived `state`:
      - 'succeeded' / 'failed' from the latest plan-kind JobRun (Postgres)
      - 'planning' from Redis active_job key (for trips with no terminal
        JobRun but a job in flight)
      - 'no_job' otherwise

    The async signature is required because trip_service.list_trips_for_user
    awaits an arq pool for the Redis MGET. See that function's docstring
    for the dual-read rationale + trip-concierge-hia for the long-term
    schema fix.
    """
    rows = await trip_service.list_trips_for_user(db, user_id=user.id)
    return TripListResponse(items=[TripListItem.model_validate(row) for row in rows])


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: uuid.UUID, user: AuthedUser, db: SessionDep) -> TripRead:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    if trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return TripRead.model_validate(trip)


@internal_router.get("/{trip_id}/active-job", response_model=ActiveJobResponse)
async def get_active_job(
    trip_id: uuid.UUID,
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
) -> ActiveJobResponse:
    """Probe whether a Redis active_job key exists for the given trip.

    Slice 4.2 tightening. Called by the PWA's fetchTripDetail helper
    when /plan/status returns 404 — distinguishes "job enqueued, worker
    hasn't written terminal JobRun yet" (PWA shows planning UI) from
    "no plan attempt ever made" (PWA shows no_job UI).

    No DB round-trip; pure Redis key existence check. No JWT user
    auth — uses INTERNAL_AUTH_SECRET header like /internal/auth/mint-
    mcp-token. The PWA server, not the browser, calls this endpoint.

    Returns {active: bool}. No information about the active job's
    job_id or kind is leaked — the PWA only needs the boolean for the
    UX branch.
    """
    expected = _internal_secret()
    if x_internal_secret is None or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    value = await redis.get(f"trip:{trip_id}:active_job")
    return ActiveJobResponse(active=value is not None)


@router.get("/{trip_id}/full", response_model=TripFullRead)
def get_trip_full(
    trip_id: uuid.UUID,
    user: AuthedUser,
    db: SessionDep,
) -> TripFullRead:
    """Trip envelope plus the full days→blocks→sources tree.

    Slice 3.3's MCP get_trip tool composes this with /plan/status to render
    the user-facing observability surface (PLANNING / SUCCEEDED / FAILED
    state). plan_status is intentionally NOT returned here — this endpoint
    stays a pure read with no Redis dependency.
    """
    trip = trip_service.get_trip_full(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    if trip.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return TripFullRead.model_validate(trip)
