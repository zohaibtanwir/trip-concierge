"""PATCH /trips/{trip_id} — settings-shaped column writes (slice 4.5b commit 1).

Per slice 4.5b Q1=B sign-off: pace and budget_total are *settings* on the
Trip row (column writes), not *rules* (append to constraints.rules[]).
Storing pace transitions in constraints.rules would break the
"rules-accumulate-over-time, settings-overwrite" mental model.

This route is the column-write counterpart to slice 3.4a's
POST /constraints (rule-append). Both share:
- The same trip-lock primitive (active_job key, KIND_LABELS, 409 path).
- The refine_trip arq task as the underlying job (PATCH is a UX
  abstraction; the job IS a refine, kind='refine' on active_job).
- The same status_url shape.

Body validator: at-least-one-of {pace, budget_total} required. Empty
PATCH is rejected at the schema layer (mirror of CreateTripInput's
at-least-destination-or-vibe pattern).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
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

router = APIRouter(prefix="/trips", tags=["settings"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


class UpdateTripSettingsRequest(BaseModel):
    """PATCH /trips/{id} body. Both fields optional; at least one required."""

    model_config = ConfigDict(extra="forbid")

    pace: Literal["packed", "balanced", "lazy"] | None = Field(
        default=None,
        description=(
            "Trip pace setting. 'packed' = max 8 blocks/day, 'balanced' "
            "= 6, 'lazy' = 4. Maps to per-day block-count cap enforced "
            "by the Logistics agent."
        ),
    )
    budget_total: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total trip budget cap as a number (trip currency). The "
            "Budget Auditor enforces this across all days; if exceeded "
            "after surgical revisions, the audit pass returns "
            "approved=false with the closest feasible plan."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one(self) -> UpdateTripSettingsRequest:
        if self.pace is None and self.budget_total is None:
            raise ValueError("at least one of `pace` or `budget_total` must be provided")
        return self


def _synthesize_settings_refinement(*, pace: str | None, budget_total: float | None) -> str:
    """Build the refinement_description for the refine_trip task.

    Mirror of services/constraint_synthesizer.synthesize_constraint_refinement's
    contract:
    - Deterministic (same args → byte-identical output).
    - Names what changed and the new value(s).
    - Reminds the crew the existing constraints still hold (additive
      to constraints.rules; doesn't relax dietary/mobility/etc.).
    """
    parts: list[str] = []
    if pace is not None:
        parts.append(f"the trip pace was updated to {pace}")
    if budget_total is not None:
        # Render as integer when whole, otherwise as-is, so prompts read
        # naturally: "budget cap of 50000" not "budget cap of 50000.0".
        rendered = (
            str(int(budget_total)) if budget_total == int(budget_total) else str(budget_total)
        )
        parts.append(f"the total budget cap is now {rendered} (trip currency)")
    change_summary = " and ".join(parts)
    return (
        f"The user updated trip settings: {change_summary}. "
        "Re-plan the itinerary to honor the new settings. This is IN "
        "ADDITION to the trip's existing constraints (see trip state); "
        "do not relax any dietary, mobility, accessibility, no-go, or "
        "other rules. The Budget Auditor must confirm the result "
        "satisfies the new settings AND all prior constraints before "
        "returning."
    )


@router.patch(
    "/{trip_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def update_trip_settings(
    trip_id: uuid.UUID,
    payload: UpdateTripSettingsRequest,
    _user: AuthedUser,
    db: SessionDep,
) -> dict[str, str]:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    active_key = f"trip:{trip_id}:active_job"

    # Active-job guard — mirror of /constraints, /refine, /regenerate etc.
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

    # Column writes BEFORE enqueue. If enqueue fails, the new settings
    # are still persisted and the user can retry without re-stating.
    # Symmetric with /constraints (append BEFORE enqueue).
    if payload.pace is not None:
        trip.pace = payload.pace
    if payload.budget_total is not None:
        trip.budget_total = Decimal(str(payload.budget_total))
    db.add(trip)
    db.commit()

    refinement_description = _synthesize_settings_refinement(
        pace=payload.pace,
        budget_total=payload.budget_total,
    )

    job = await redis.enqueue_job("refine_trip", str(trip_id), refinement_description)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue refine job for the new settings",
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
