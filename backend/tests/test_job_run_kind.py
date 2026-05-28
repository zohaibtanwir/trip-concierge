"""JobRun.kind column — added in slice 3.3 migration 0006.

Three valid values: 'plan' (create_trip's enqueued job), 'refine'
(refine_trip's hierarchical-crew job), 'regen' (regenerate_day's
day-scoped job). The status endpoint and the new GET /full endpoint
read this column to render job history honestly.

Backward-compat: server_default='plan' means existing inserts that
don't specify kind (every call site before slice 3.3) still get
'plan' automatically. No code changes needed in callers until
slices 3.3c/d wire refine/regen paths.

Migration 0006 also bumps the alembic head — the startup check
test (test_startup_check.test_passes_when_db_at_head) verifies
DB-head match without naming a version, so it keeps passing.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.models.trip import Trip
from app.models.user import User


def _make_trip(db: Session) -> Trip:
    user = User(email=f"kind-{uuid.uuid4()}@test.com", name="Kind Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def test_job_run_kind_defaults_to_plan_when_omitted(db_session: Session) -> None:
    """Existing call sites (worker.py, plan endpoint) don't pass kind.
    The server_default keeps them producing kind='plan' rows — no
    backward-incompat with pre-3.3 writes.
    """
    trip = _make_trip(db_session)
    row = JobRun(
        job_id=uuid.uuid4().hex[:16],
        trip_id=trip.id,
        status="succeeded",
        approved=True,
        agent_summary=[],
        total_tokens=0,
        total_cost=Decimal("0"),
        total_duration_ms=1000,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.kind == "plan"


def test_job_run_accepts_refine_kind(db_session: Session) -> None:
    """Slice 3.3 refine_trip worker will write kind='refine'."""
    trip = _make_trip(db_session)
    row = JobRun(
        job_id=uuid.uuid4().hex[:16],
        trip_id=trip.id,
        kind="refine",
        status="succeeded",
        approved=True,
        agent_summary=[],
        total_tokens=0,
        total_cost=Decimal("0"),
        total_duration_ms=1000,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.kind == "refine"


def test_job_run_accepts_regen_kind(db_session: Session) -> None:
    """Slice 3.3 regenerate_day worker will write kind='regen'."""
    trip = _make_trip(db_session)
    row = JobRun(
        job_id=uuid.uuid4().hex[:16],
        trip_id=trip.id,
        kind="regen",
        status="succeeded",
        approved=True,
        agent_summary=[],
        total_tokens=0,
        total_cost=Decimal("0"),
        total_duration_ms=1000,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.kind == "regen"
