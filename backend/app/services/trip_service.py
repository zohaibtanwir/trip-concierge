"""Trip persistence — thin layer between routes and the ORM."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import case, delete, select, true
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.trip import Trip
from app.models.user_source import UserSource
from app.schemas.trip import TripCreate

logger = logging.getLogger(__name__)

_LIST_TRIPS_LIMIT = 50


def create_trip(db: Session, payload: TripCreate, *, user_id: uuid.UUID) -> Trip:
    """Create a Trip row owned by the given user_id.

    Slice 3.2 separated user_id from the request body — it now comes
    from the JWT subject via the route's auth dependency, not from
    untrusted input.
    """
    trip = Trip(user_id=user_id, **payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def get_trip(db: Session, trip_id: uuid.UUID) -> Trip | None:
    return db.get(Trip, trip_id)


async def _planning_trip_ids(
    trip_ids: list[uuid.UUID],
    redis: Any,
) -> set[uuid.UUID]:
    """Subset of trip_ids that have a Redis active_job key set.

    Single MGET round-trip regardless of N. Returns trip_ids whose
    `trip:{id}:active_job` key is non-None (i.e. a planning/refine/regen
    job is in flight). Empty input returns the empty set without touching
    Redis.

    Graceful degradation: on ConnectionError, TimeoutError, or any other
    Redis exception the helper logs a warning and returns the empty set.
    Callers see the same result as "no active jobs found" — affected
    trips fall through to derived state 'no_job', which is the same
    state they'd carry if Redis were never consulted. This keeps the
    list endpoint up under a Redis outage; the cost is a temporary loss
    of the 'planning' badge until Redis recovers.

    Accepts the Redis client via parameter (not module-level) so tests
    can inject a mock without patching create_pool.
    """
    if not trip_ids:
        return set()
    keys = [f"trip:{tid}:active_job" for tid in trip_ids]
    try:
        values = await redis.mget(keys)
    except Exception as e:  # noqa: BLE001 — graceful-degradation by design
        logger.warning(
            "redis mget failed for trip-list planning-state check; "
            "treating affected trips as no_job. error_class=%s",
            type(e).__name__,
        )
        return set()
    return {tid for tid, value in zip(trip_ids, values, strict=True) if value is not None}


async def list_trips_for_user(db: Session, *, user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return a user's trips with derived `state` per slice 4.2.

    Two stores compose the derived state:

      1. Postgres LATERAL JOIN — terminal state from the latest plan-kind
         JobRun row.
      2. Redis MGET — 'planning' overlay for trips with no terminal
         JobRun but an active_job key present (queued/running phase, not
         yet persisted to Postgres).

    SQL shape (step 1):

        SELECT trips.*,
               CASE WHEN lp.status = 'succeeded' THEN 'succeeded'
                    WHEN lp.status IN ('failed','cancelled') THEN 'failed'
                    ELSE 'no_job'
               END AS state
        FROM trips
        LEFT JOIN LATERAL (
            SELECT status
            FROM job_runs
            WHERE trip_id = trips.id AND kind = 'plan'
            ORDER BY created_at DESC
            LIMIT 1
        ) lp ON TRUE
        WHERE trips.user_id = :user_id
        ORDER BY trips.created_at DESC
        LIMIT 50;

    The LATERAL subquery's WHERE references the outer Trip.id — that's
    what makes it LATERAL. LEFT JOIN (not INNER) keeps trips with no
    JobRun in the result set (state='no_job'). The kind='plan' filter is
    load-bearing: refine and regen JobRuns must not influence the trip's
    list-page state.

    Step 2 (Redis MGET) is narrowed to only the trips where step 1
    derived state='no_job' — succeeded/failed trips with an active
    refine/regen are intentionally NOT promoted to 'planning' (the plan
    state is the surface here; refine progress lives on the detail page).

    Why two stores: JobRun.status is terminal-only by design (worker
    writes one row on succeeded|failed|cancelled). 'queued'/'running'
    state lives in Redis. The list page needs all four UX states to
    avoid confusing UX on a just-submitted trip ("Not started" badge
    when planning is actually in flight). See `trip-concierge-hia` for
    the long-term schema fix that eliminates this dual-read.

    Returns plain dicts (not ORM rows) because the SELECT emits a
    derived column the ORM doesn't own. Trade-off accepted: routes
    layer turns each dict into a TripListItem via Pydantic.
    """
    latest_plan = (
        select(JobRun.status.label("status"))
        .where(JobRun.trip_id == Trip.id, JobRun.kind == "plan")
        .order_by(JobRun.created_at.desc())
        .limit(1)
        .lateral("latest_plan")
    )

    state_col = case(
        (latest_plan.c.status == "succeeded", "succeeded"),
        (latest_plan.c.status.in_(["failed", "cancelled"]), "failed"),
        else_="no_job",
    ).label("state")

    stmt = (
        select(Trip, state_col)
        .outerjoin(latest_plan, true())
        .where(Trip.user_id == user_id)
        .order_by(Trip.created_at.desc())
        .limit(_LIST_TRIPS_LIMIT)
    )

    # Materialize the rows since we iterate twice (once for the
    # no_job-narrowing, once for the final dict comprehension).
    rows = db.execute(stmt).all()

    # Narrow the Redis MGET to only the no_job trips. The 'planning'
    # overlay applies only when SQL didn't already give us a terminal
    # state. This both reduces Redis key fan-out and encodes the policy
    # that succeeded/failed trips with an active refine are NOT shown as
    # 'planning' in the list.
    no_job_trip_ids = [trip.id for trip, state in rows if state == "no_job"]
    planning_ids: set[uuid.UUID] = set()
    if no_job_trip_ids:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        planning_ids = await _planning_trip_ids(no_job_trip_ids, redis)

    return [
        {
            "id": trip.id,
            "destination": trip.destination,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "currency": trip.currency,
            "budget_total": trip.budget_total,
            "state": ("planning" if (state == "no_job" and trip.id in planning_ids) else state),
            "created_at": trip.created_at,
        }
        for trip, state in rows
    ]


def persist_regenerated_day(
    db: Session,
    *,
    trip_id: uuid.UUID,
    day_number: int,
    blocks: list[dict[str, Any]],
) -> None:
    """Replace a single Day's blocks with new ones. Slice 3.3 commit 4.

    Surgical update — other days for this trip are untouched. Locked-block
    handling is the worker's responsibility (splice locked blocks into the
    input list before calling this function); this layer writes exactly
    what it receives.

    Raises ValueError if the trip has no Day with the given day_number —
    that's an invariant break the worker shouldn't have triggered, so
    failing loudly here surfaces it instead of silently creating orphan
    blocks under a nonexistent day.
    """
    day = db.execute(
        select(Day).where(Day.trip_id == trip_id, Day.day_number == day_number)
    ).scalar_one_or_none()
    if day is None:
        raise ValueError(f"trip {trip_id} has no day {day_number}")

    # Drop existing blocks; sources cascade via ondelete=CASCADE.
    db.execute(delete(Block).where(Block.day_id == day.id))
    db.flush()

    for block_dict in blocks:
        block = Block(
            day_id=day.id,
            order=int(block_dict["order"]),
            type=str(block_dict["type"]),
            venue_name=str(block_dict["venue_name"]),
            start_time=block_dict.get("start_time"),
            duration_minutes=int(block_dict.get("duration_minutes") or 0),
            est_cost=_to_decimal(block_dict.get("est_cost")),
            currency=str(block_dict.get("currency") or "USD"),
            notes=str(block_dict.get("notes") or ""),
        )
        db.add(block)
        db.flush()
        for url in block_dict.get("source_urls") or []:
            db.add(Source(block_id=block.id, url=str(url)))

    db.commit()


def get_trip_full(db: Session, trip_id: uuid.UUID) -> Trip | None:
    """Fetch a Trip with its days→blocks→sources tree eager-loaded.

    Three queries total via selectinload, regardless of how many days or
    blocks the trip has — avoids the N+1 pattern a naive query would hit.
    Day.blocks and Trip.days carry `order_by` on the relationship, so the
    loaded collections are pre-sorted by the time they reach the route.

    Returns None if the trip doesn't exist.
    """
    stmt = (
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.days).selectinload(Day.blocks).selectinload(Block.sources))
    )
    return db.execute(stmt).scalar_one_or_none()


def persist_audited_plan(
    db: Session,
    trip_id: uuid.UUID,
    audited: dict[str, Any],
) -> None:
    """Replace a Trip's Days/Blocks/Sources with rows from an AuditedPlan dict.

    Destructive-overwrite by design: the trip's existing Days are deleted
    (CASCADE removes Blocks and Sources), then new rows are inserted from
    `audited["days"]`. Intended for `POST /trips/{id}/plan` (slice 2.5) and
    full-trip regen tools (Phase 3). Per-block edits use a narrower path.

    Audited shape (from agents.schemas.AuditedPlan.model_dump()):
        {
            "days": [
                {
                    "day_number": int,
                    "date": str | None,
                    "summary": str,
                    "blocks": [
                        {
                            "order": int,
                            "type": "venue"|"transit"|"meal"|"rest",
                            "venue_name": str,
                            "start_time": str | None,
                            "duration_minutes": int,
                            "est_cost": float | None,
                            "currency": str,
                            "source_urls": [str, ...],
                            ...  # extra fields tolerated and ignored
                        },
                    ],
                },
            ],
            ...  # audit metadata (approved, revision_log, etc.) — slice 2.5b persists this
                 # to JobRun rows from the arq worker; this function only writes itinerary content.
        }
    """
    # Wipe existing Days for this trip; CASCADE handles Blocks + Sources.
    db.execute(delete(Day).where(Day.trip_id == trip_id))

    for day_dict in audited.get("days") or []:
        day = Day(
            trip_id=trip_id,
            day_number=int(day_dict["day_number"]),
            date=_parse_date(day_dict.get("date")),
            summary=str(day_dict.get("summary") or ""),
        )
        db.add(day)
        db.flush()  # populate day.id for block FK

        for block_dict in day_dict.get("blocks") or []:
            block = Block(
                day_id=day.id,
                order=int(block_dict["order"]),
                type=str(block_dict["type"]),
                venue_name=str(block_dict["venue_name"]),
                start_time=block_dict.get("start_time"),
                duration_minutes=int(block_dict.get("duration_minutes") or 0),
                est_cost=_to_decimal(block_dict.get("est_cost")),
                currency=str(block_dict.get("currency") or "USD"),
                notes=str(block_dict.get("notes") or ""),
            )
            db.add(block)
            db.flush()  # populate block.id for source FK

            for url in block_dict.get("source_urls") or []:
                db.add(Source(block_id=block.id, url=str(url)))

    db.commit()


def _parse_date(raw: Any) -> date_type | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date_type):
        return raw
    return date_type.fromisoformat(str(raw))


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    return Decimal(str(raw))


def append_constraint(
    db: Session,
    *,
    trip_id: uuid.UUID,
    kind: str,
    value: Any,
    raw_text: str,
) -> Trip:
    """Append a constraint to Trip.constraints["rules"] with (kind, value) dedup.

    Slice 3.4a Q1: the wrap pattern. Trip.constraints stays a flexible
    JSONB dict; we add a "rules" key (list of constraint dicts) without
    disturbing any other keys the column may hold. Dedup compares
    (kind, value) only — raw_text and created_at vary per call and must
    not defeat the dedup invariant.

    First-call raw_text wins on dedup: a user re-sending "I'm vegetarian"
    with slightly different wording doesn't overwrite the original.

    Raises ValueError on unknown trip_id — failing loudly surfaces an
    invariant break in the caller rather than silently no-op'ing.
    """
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise ValueError(f"trip {trip_id} not found")

    # Copy so SQLAlchemy notices the JSONB mutation. dict.copy() is enough
    # because we replace the "rules" key entirely; we don't mutate nested
    # dicts in place.
    constraints = dict(trip.constraints or {})
    rules: list[dict[str, Any]] = list(constraints.get("rules") or [])

    # Dedup by (kind, value). First-call raw_text and created_at preserved.
    for existing in rules:
        if existing.get("kind") == kind and existing.get("value") == value:
            return trip  # no-op

    rules.append(
        {
            "kind": kind,
            "value": value,
            "raw_text": raw_text,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    constraints["rules"] = rules
    trip.constraints = constraints
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def append_user_source(
    db: Session,
    *,
    trip_id: uuid.UUID,
    url: str | None,
    raw_text: str,
    content_type: str,
) -> UserSource:
    """Persist one row to user_sources for the given trip.

    No dedup. v1.0a treats each call as intentional — a user pasting
    the same URL twice may be re-fetching after content changed.
    Symmetric with append_constraint's ValueError-on-missing-trip
    discipline.

    The route layer translates ValueError → 404. Programmatic callers
    that skip the pre-check get a loud failure rather than a silent
    orphan write.
    """
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise ValueError(f"trip {trip_id} not found")

    row = UserSource(
        trip_id=trip_id,
        url=url,
        raw_text=raw_text,
        content_type=content_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
