"""POST /trips/{trip_id}/plan — enqueue a crew-planning job.

Returns 202 Accepted with `{job_id, status_url}` in <1s. The actual
4-agent crew runs in the background via `app.worker.plan_trip`.
Slice 2.5c adds the status endpoint.

Idempotency: a Redis key `trip:{trip_id}:active_job` holds the job_id
of an in-flight planning job. If present, returns 409. The worker
clears the key on terminal events (success / failure / cancel) — see
app.worker.

The handler is async because arq's pool API is async. SQLAlchemy
session calls are sync; that's a minor blocking-the-event-loop tax
on a single get_trip query — acceptable here, would matter at scale.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from trip_agents.schemas import TripRunRequest

from app.config import settings
from app.db.session import get_session
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["plan"])

SessionDep = Annotated[Session, Depends(get_session)]

# Redis key holding the active job_id for a given trip. TTL matches the
# worker's job_timeout so orphaned keys clear themselves even if the
# worker process crashes without writing a JobRun.
_ACTIVE_JOB_KEY_TTL_SECONDS = 900


def _build_request(trip: Any) -> TripRunRequest:
    """Snapshot the Trip row into a TripRunRequest payload.

    The worker MUST NOT re-read the trips row mid-run (slice 2.5b
    architecture decision) — this dict IS the snapshot.
    """
    return TripRunRequest(
        destination=trip.destination,
        start_date=str(trip.start_date) if trip.start_date else None,
        end_date=str(trip.end_date) if trip.end_date else None,
        group_size=trip.group_size,
        budget_total=float(trip.budget_total) if trip.budget_total is not None else None,
        currency=trip.currency,
        # pace is `str` in the DB and `Literal["packed","balanced","lazy"]` in the
        # schema. If the DB ever holds a value outside the literal set, this raises
        # 422 — which is the right behavior.
        pace=trip.pace,
        # Soft inputs that don't fit in a column live in trip.constraints (JSONB).
        # Slice 2.5b leaves them empty in the snapshot; F4-style structured
        # constraints get serialized into these fields in a later slice.
        vibe="",
        constraints="",
        user_sources="",
        dietary="",
        mobility="",
        no_go_list="",
    )


@router.post(
    "/{trip_id}/plan",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_plan(trip_id: uuid.UUID, db: SessionDep) -> dict[str, str]:
    """Enqueue a crew-planning job. Returns immediately with a job_id."""
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    request = _build_request(trip)

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    active_key = f"trip:{trip_id}:active_job"

    existing = await redis.get(active_key)
    if existing is not None:
        existing_id = existing.decode() if isinstance(existing, bytes) else str(existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"a planning job is already in progress for trip {trip_id} "
                f"(job {existing_id}); cancel via DELETE /trips/{trip_id}/plan "
                "before retrying"
            ),
        )

    job = await redis.enqueue_job("plan_trip", str(trip_id), request.model_dump())
    if job is None:
        # arq returns None if the queue rejected the job — e.g. a job with the
        # same _job_id is already enqueued. We don't pass _job_id, so this is
        # an unexpected infra failure.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue plan job",
        )

    await redis.setex(active_key, _ACTIVE_JOB_KEY_TTL_SECONDS, job.job_id)

    return {
        "job_id": job.job_id,
        "status_url": f"/trips/{trip_id}/plan/status",
    }
