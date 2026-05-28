"""POST /trips/{trip_id}/plan and GET/DELETE companions — Slice 2.5b + 2.5c.

POST  /trips/{id}/plan        → enqueue a crew-planning job, return 202 + job_id
GET   /trips/{id}/plan/status → poll lifecycle + outcome (see schemas.plan)
DELETE /trips/{id}/plan       → cancel an in-flight job

State machine (consumed by GET):

    queued ──► running ──► done (+ approved={true|false})
                  │
                  └──► cancelling ──► cancelled       (DELETE in flight)

                  └──► failed                          (worker raised)

Redis keys this module owns:

  trip:{id}:active_job   — job_id of an in-flight planning job (TTL 900s).
                           Set by POST, deleted by DELETE or by the worker
                           on terminal events.
  trip:{id}:progress     — JSON-serialized ProgressUpdate; latest worker step.
                           Best-effort; missing/malformed = treat as None.
  trip:{id}:cancelling   — Tombstone written by DELETE BEFORE abort_job, so
                           GET never returns 404 in the gap between DELETE
                           returning 204 and the worker writing JobRun.
                           Deleted by the worker's CancelledError handler.
                           TTL 30s as a self-healing backstop.

Async handlers because arq's pool API is async. SQLAlchemy session calls
are sync; that's a minor blocking-the-event-loop tax on small lookups —
acceptable here, would matter at scale.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any

from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from trip_agents.schemas import TripRunRequest

from app.config import settings
from app.db.session import get_session
from app.models.job_run import JobRun
from app.schemas.plan import JobKind, PlanState, PlanStatus, ProgressUpdate
from app.services import trip_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trips", tags=["plan"])

SessionDep = Annotated[Session, Depends(get_session)]

# Redis key holding the active job_id for a given trip. TTL matches the
# worker's job_timeout so orphaned keys clear themselves even if the
# worker process crashes without writing a JobRun.
_ACTIVE_JOB_KEY_TTL_SECONDS = 900

# Cancelling tombstone TTL — generous enough to cover the worker's
# CancelledError → JobRun write path (sub-second in practice) plus DB
# commit latency, short enough that a crashed worker doesn't leave the
# trip stuck in "cancelling" forever.
_CANCELLING_TTL_SECONDS = 30


def _decode(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


# Slice 3.3: the active_job Redis value widened from a plain string
# (just the arq job_id) to JSON carrying both job_id and kind. Refine
# and regen routes write the same key with their own kind label, and
# GET /status surfaces it back via PlanStatus.kind.
KIND_LABELS: dict[str, str] = {
    "plan": "planning",
    "refine": "refinement",
    "regen": "day regeneration",
}


def encode_active_value(*, job_id: str, kind: JobKind) -> str:
    """Build the JSON payload written to trip:{id}:active_job."""
    return json.dumps({"job_id": job_id, "kind": kind})


def decode_active_value(raw: bytes | str | None) -> tuple[str, str] | None:
    """Return (job_id, kind) from the active_job Redis value, or None
    if the key is absent.

    Tolerates legacy plain-string entries (anything written by pre-3.3
    code that didn't know about kind) by treating them as kind='plan'.
    Graceful degradation, not a crash — the value's only purpose is
    routing follow-up calls, and 'plan' is the right default for legacy.
    """
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "job_id" in obj:
            return str(obj["job_id"]), str(obj.get("kind", "plan"))
    except (json.JSONDecodeError, TypeError):
        pass
    return text, "plan"


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

    job = await redis.enqueue_job("plan_trip", str(trip_id), request.model_dump())
    if job is None:
        # arq returns None if the queue rejected the job — e.g. a job with the
        # same _job_id is already enqueued. We don't pass _job_id, so this is
        # an unexpected infra failure.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue plan job",
        )

    await redis.setex(
        active_key,
        _ACTIVE_JOB_KEY_TTL_SECONDS,
        encode_active_value(job_id=job.job_id, kind="plan"),
    )

    return {
        "job_id": job.job_id,
        "status_url": f"/trips/{trip_id}/plan/status",
    }


def _parse_progress(raw: bytes | str | None) -> ProgressUpdate | None:
    """Tolerant parse — partial writes or schema drift return None, never 500."""
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
        return ProgressUpdate.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def _latest_job_run(db: Session, trip_id: uuid.UUID) -> JobRun | None:
    stmt = (
        select(JobRun).where(JobRun.trip_id == trip_id).order_by(JobRun.created_at.desc()).limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


_TERMINAL_TO_STATE: dict[str, PlanState] = {
    "succeeded": "done",
    "failed": "failed",
    "cancelled": "cancelled",
}


@router.get("/{trip_id}/plan/status", response_model=PlanStatus)
async def get_plan_status(trip_id: uuid.UUID, db: SessionDep) -> PlanStatus:
    """Poll the lifecycle + outcome of a planning job.

    Resolution order — first match wins:
      1. `trip:{id}:cancelling`         → state="cancelling"
      2. `trip:{id}:active_job` + arq   → state="queued" | "running"
      3. latest JobRun row              → state="done" | "failed" | "cancelled"
      4. nothing                        → 404

    Step 1 must precede step 2 — during a DELETE race, active_job is still
    set briefly. Without the tombstone check, GET would report "running"
    for a job the user has already cancelled, and the UI would not show
    the cancelling indicator.
    """
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    cancelling = await redis.get(f"trip:{trip_id}:cancelling")
    if cancelling is not None:
        return PlanStatus(state="cancelling", trip_url=f"/trips/{trip_id}")

    active = decode_active_value(await redis.get(f"trip:{trip_id}:active_job"))
    if active is not None:
        active_job, active_kind = active
        kind_typed: JobKind | None = (
            active_kind if active_kind in ("plan", "refine", "regen") else None  # type: ignore[assignment]
        )
        arq_status = await Job(active_job, redis=redis).status()
        progress_raw = await redis.get(f"trip:{trip_id}:progress")
        if arq_status == JobStatus.queued:
            return PlanStatus(
                state="queued",
                job_id=active_job,
                kind=kind_typed,
                trip_url=f"/trips/{trip_id}",
            )
        return PlanStatus(
            state="running",
            job_id=active_job,
            kind=kind_typed,
            progress_message=_parse_progress(progress_raw),
            trip_url=f"/trips/{trip_id}",
        )

    job_run = _latest_job_run(db, trip_id)
    if job_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no planning job found for trip {trip_id}",
        )

    resolved_state = _TERMINAL_TO_STATE.get(job_run.status)
    if resolved_state is None:
        # Defensive: an unexpected status string in the DB. Fail loudly
        # rather than silently mapping to "failed" — easier to debug.
        logger.error(
            "plan.status.unknown_job_run_status",
            extra={"trip_id": str(trip_id), "status": job_run.status},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"unrecognized job_run status: {job_run.status}",
        )

    return PlanStatus(
        state=resolved_state,
        job_id=job_run.job_id,
        approved=job_run.approved if resolved_state == "done" else None,
        error=job_run.error,
        started_at=job_run.started_at.isoformat() if job_run.started_at else None,
        finished_at=job_run.finished_at.isoformat() if job_run.finished_at else None,
        trip_url=f"/trips/{trip_id}",
    )


@router.delete("/{trip_id}/plan", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_plan(trip_id: uuid.UUID, db: SessionDep) -> Response:
    """Cancel an in-flight planning job. Idempotent during the cancelling window.

    Semantics:
      - active_job present  → set tombstone, abort_job, delete active_job → 204
      - tombstone present   → idempotent 204 (worker is still finishing up)
      - no active, terminal → 409 (already done — read GET /status for outcome)
      - nothing at all      → 404
    """
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    active_key = f"trip:{trip_id}:active_job"
    cancelling_key = f"trip:{trip_id}:cancelling"

    active = decode_active_value(await redis.get(active_key))
    if active is not None:
        active_job, _ = active
        # Tombstone BEFORE abort_job so GET-after-DELETE never sees a 404.
        # The worker's CancelledError handler deletes the tombstone after
        # writing JobRun(status="cancelled"); the 30s TTL is a backstop.
        await redis.setex(cancelling_key, _CANCELLING_TTL_SECONDS, "1")
        # arq 0.28 puts the abort signal on Job, not on the pool. The pool
        # publishes to abort_jobs_ss via this method.
        await Job(active_job, redis=redis).abort()
        await redis.delete(active_key)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # No active job. Disambiguate "nothing to cancel" from "already done".
    if await redis.get(cancelling_key) is not None:
        # Worker still finishing the cancel — second DELETE is idempotent.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if _latest_job_run(db, trip_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"trip {trip_id} has no in-flight planning job; the latest "
                "job has already completed (read GET /plan/status for outcome)"
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"no planning job found for trip {trip_id}",
    )
