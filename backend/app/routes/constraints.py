"""POST /trips/{trip_id}/constraints — append a constraint + enqueue refine.

Slice 3.4a commit 2. The route:
1. Validates input (Pydantic forbids unknown kinds + requires text).
2. Loads the Trip — 404 if missing.
3. Checks the slice-3.3 active_job key — 409 if any job is in flight.
   Reuses decode_active_value + KIND_LABELS from app.services.trip_lock
   (extracted in slice 4.5b for ownership clarity — see that module's
   docstring for the rationale).
4. Appends the constraint to Trip.constraints["rules"] via the commit-1
   storage helper. The append happens BEFORE the enqueue — if enqueue
   fails, the constraint is still persisted and the user can retry.
5. Synthesizes a deterministic refinement_description and enqueues the
   existing refine_trip arq task (slice 3.3 commit 3). No new JobKind —
   the underlying job IS a refine; add_constraint is a UX abstraction.
6. Writes the active_job JSON with kind="refine".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

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
from app.services.constraint_synthesizer import synthesize_constraint_refinement
from app.services.trip_lock import (
    ACTIVE_JOB_KEY_TTL_SECONDS,
    KIND_LABELS,
    decode_active_value,
    encode_active_value,
)

router = APIRouter(prefix="/trips", tags=["constraints"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]

# When adding a kind here, also add a per-kind framing branch in
# services/constraint_synthesizer.py:_framing_for_kind() — the
# generic fall-through is acceptable but ships less-specific
# semantic framing to the refine worker.
ConstraintKind = Literal[
    "budget", "dietary", "mobility", "no_go", "walking_limit", "accessibility", "custom"
]


class AddConstraintRequest(BaseModel):
    """POST /trips/{id}/constraints body."""

    model_config = ConfigDict(extra="forbid")

    constraint_text: str = Field(
        min_length=3,
        max_length=500,
        description=(
            "Free-text statement of the constraint, as the user said it. "
            "Used as both the structured value (for dedup) and the raw "
            "text (for the prompt). For v1.0, dedup is literal-string."
        ),
    )
    constraint_kind: ConstraintKind = Field(
        default="custom",
        description="Constraint category for indexing and per-kind framing.",
    )


@router.post(
    "/{trip_id}/constraints",
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_constraint(
    trip_id: uuid.UUID,
    payload: AddConstraintRequest,
    _user: AuthedUser,
    db: SessionDep,
) -> dict[str, str]:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    active_key = f"trip:{trip_id}:active_job"

    # Active-job check using the slice-3.3 helpers — reuse, don't reinvent.
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

    # Persist the constraint BEFORE enqueueing. If enqueue fails, the
    # constraint is still recorded; user can retry without re-stating.
    trip_service.append_constraint(
        db,
        trip_id=trip_id,
        kind=payload.constraint_kind,
        value=payload.constraint_text,
        raw_text=payload.constraint_text,
    )

    # Synthesize the refinement_description and enqueue the existing
    # refine_trip task. No new arq task; no new JobKind.
    refinement_description = synthesize_constraint_refinement(
        kind=payload.constraint_kind,
        value=payload.constraint_text,
        raw_text=payload.constraint_text,
    )

    job = await redis.enqueue_job("refine_trip", str(trip_id), refinement_description)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue refine job for the new constraint",
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
