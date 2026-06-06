"""POST /trips/{trip_id}/refine — enqueue a hierarchical refine job.

Slice 3.3 commit 3. Mirrors the POST /plan handler from 2.5b but with
two intentional differences:

- Auth-required (Depends(require_mcp_token)) — new routes adopt the
  slice-3.2 pattern; auth on the older POST /plan is tracked as a
  separate followup.
- Writes JSON to the active_job Redis key: {"job_id":"...","kind":"refine"}.
  Shared key + shared cancelling mechanism with /plan and /regenerate;
  one DELETE /plan route cancels whatever's in flight.

The refinement_description (free-text) is the load-bearing input. The
trip state (current days/blocks) is loaded by the worker from the DB at
job-start time — NOT snapshotted into the enqueue payload, because
unlike create_trip the planning context is already persisted.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.services import trip_service
from app.services.trip_lock import (
    ACTIVE_JOB_KEY_TTL_SECONDS,
    KIND_LABELS,
    decode_active_value,
    encode_active_value,
)

router = APIRouter(prefix="/trips", tags=["refine"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


class RefineRequest(BaseModel):
    """POST /trips/{id}/refine body."""

    model_config = ConfigDict(extra="forbid")

    refinement_description: str = Field(
        min_length=1,
        max_length=2000,
        description="Free-text refinement instruction (e.g., 'make Day 2 chiller').",
    )


@router.post(
    "/{trip_id}/refine",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_refine(
    trip_id: uuid.UUID,
    payload: RefineRequest,
    _user: AuthedUser,
    db: SessionDep,
) -> dict[str, str]:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    active_key = f"trip:{trip_id}:active_job"

    existing = await redis.get(active_key)
    if existing is not None:
        existing_id, existing_kind = decode_active_value(existing)  # type: ignore[misc]
        label = KIND_LABELS.get(existing_kind, "background")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"a {label} job is already in progress for trip {trip_id} "
                f"(job {existing_id}); cancel via DELETE /trips/{trip_id}/plan "
                "before retrying"
            ),
        )

    job = await redis.enqueue_job(
        "refine_trip",
        str(trip_id),
        payload.refinement_description,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue refine job",
        )

    await redis.setex(
        active_key,
        ACTIVE_JOB_KEY_TTL_SECONDS,
        encode_active_value(job_id=job.job_id, kind="refine"),
    )

    return {
        "job_id": job.job_id,
        "status_url": f"/trips/{trip_id}/plan/status",
    }
