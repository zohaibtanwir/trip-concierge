"""POST /trips/{trip_id}/days/{day_number}/regenerate — enqueue a day-scoped
regen job.

Slice 3.3 commit 3. Same shape as POST /refine: auth-required, active-job
check, JSON Redis value with kind='regen', 202 with {job_id, status_url}.

Day-number validation: Path(ge=1, le=30) refuses 0, negatives, and absurd
values at the route layer. "Does this trip actually have a Day N?" is the
worker's responsibility — the route just enqueues.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.routes.plan import (
    KIND_LABELS,
    decode_active_value,
    encode_active_value,
)
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["regenerate"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]

_ACTIVE_JOB_KEY_TTL_SECONDS = 900


class RegenerateRequest(BaseModel):
    """POST /trips/{id}/days/{n}/regenerate body. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    hint: str | None = Field(
        default=None,
        max_length=500,
        description="Optional free-text guidance (e.g., 'more food, less hiking').",
    )


@router.post(
    "/{trip_id}/days/{day_number}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_regenerate(
    trip_id: uuid.UUID,
    _user: AuthedUser,
    db: SessionDep,
    day_number: Annotated[int, Path(ge=1, le=30)],
    payload: RegenerateRequest | None = None,
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

    hint = payload.hint if payload else None
    job = await redis.enqueue_job(
        "regenerate_day",
        str(trip_id),
        day_number,
        hint,
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue regenerate job",
        )

    await redis.setex(
        active_key,
        _ACTIVE_JOB_KEY_TTL_SECONDS,
        encode_active_value(job_id=job.job_id, kind="regen"),
    )

    return {
        "job_id": job.job_id,
        "status_url": f"/trips/{trip_id}/plan/status",
    }
