"""POST /trips/{trip_id}/plan — enqueue path tests.

No real Redis: `arq.create_pool` is patched to return an `AsyncMock`.
The worker tests in test_worker.py cover the consumption side; this
file covers the route side and verifies the contract between them
(task name, arg shape, idempotency, status codes).

If `app.routes.plan.create_pool` ever moves to a different import
path, these tests must follow it — wrong patch path returns a real
arq pool, the route then tries to talk to localhost:6379, and in CI
the redis service container makes the connection succeed and the
test then silently sends a real job to the queue. The `mocked.enqueue_job.called`
assertion is the load-bearing guard against that drift.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User


def _make_trip(db: Session) -> Trip:
    user = User(email=f"plan-{uuid.uuid4()}@test.com", name="Plan Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    trip = Trip(
        user_id=user.id,
        destination="Goa, India",
        currency="INR",
        group_size=2,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def _mock_pool(*, existing_active_job: bytes | None = None, job_id: str = "abc123") -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    job = MagicMock()
    job.job_id = job_id
    pool.enqueue_job.return_value = job
    pool.setex.return_value = True
    return pool


def test_returns_202_with_job_id_and_status_url(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    pool = _mock_pool(job_id="job-xyz")
    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.post(f"/trips/{trip.id}/plan")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"] == "job-xyz"
    assert body["status_url"] == f"/trips/{trip.id}/plan/status"

    # Verify the enqueue happened with the right task name + args.
    assert pool.enqueue_job.called, (
        "enqueue_job was not invoked — patch target may be wrong. The route "
        "would have hit real Redis, and a passing CI run would silently push "
        "real jobs onto the queue."
    )
    enqueue_args = pool.enqueue_job.call_args
    assert enqueue_args.args[0] == "plan_trip"
    assert enqueue_args.args[1] == str(trip.id)

    # The third arg is the TripRunRequest dict — verify it carries the
    # Trip's snapshot fields.
    request_dict = enqueue_args.args[2]
    assert request_dict["destination"] == "Goa, India"
    assert request_dict["currency"] == "INR"
    assert request_dict["group_size"] == 2
    assert request_dict["pace"] == "balanced"

    # Active-job key was set with a JSON payload + TTL. Slice 3.3 commit 3
    # widened the Redis value format from a plain string to JSON carrying
    # both job_id and kind, so refine/regen routes can write the same key
    # with their own kind label and GET /status can surface what's in flight.
    setex_args = pool.setex.call_args
    assert setex_args.args[0] == f"trip:{trip.id}:active_job"
    assert setex_args.args[1] == 900  # job_timeout
    payload = json.loads(setex_args.args[2])
    assert payload == {"job_id": "job-xyz", "kind": "plan"}


def test_returns_404_when_trip_does_not_exist(client: TestClient) -> None:
    bogus_id = uuid.uuid4()
    pool = _mock_pool()
    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.post(f"/trips/{bogus_id}/plan")

    assert response.status_code == 404
    assert not pool.enqueue_job.called, "shouldn't enqueue when the trip is missing"


def test_returns_409_when_active_job_exists_legacy_plain_string(
    client: TestClient, db_session: Session
) -> None:
    """A plain-string entry in the active_job key (written by pre-3.3 code
    or by a stale uvicorn) is tolerated: the route treats it as
    kind='plan' and surfaces the legacy job_id verbatim in the 409.
    Graceful degradation, not a crash.
    """
    trip = _make_trip(db_session)
    pool = _mock_pool(existing_active_job=b"already-running")
    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.post(f"/trips/{trip.id}/plan")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "already in progress" in detail
    assert "already-running" in detail
    # Legacy plain-string entries collapse to kind='plan', so the label
    # 'planning' surfaces in the message — same UX as a JSON entry with
    # kind='plan'.
    assert "planning" in detail
    assert not pool.enqueue_job.called


def test_returns_409_with_kind_aware_message_for_refine_in_flight(
    client: TestClient, db_session: Session
) -> None:
    """A refine job in flight surfaces in the 409 message as 'refinement'
    — the human-readable label for kind='refine'. The MCP tool layer
    relies on this to tell the user what kind of job is blocking.
    """
    trip = _make_trip(db_session)
    existing = json.dumps({"job_id": "refine-old", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing)
    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.post(f"/trips/{trip.id}/plan")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "refinement" in detail
    assert "refine-old" in detail
    assert not pool.enqueue_job.called


def test_request_snapshot_includes_dates_and_budget(
    client: TestClient, db_session: Session
) -> None:
    """Trip rows with start_date/end_date/budget_total propagate into the
    TripRunRequest snapshot the worker receives.
    """
    user = User(email=f"plan-snap-{uuid.uuid4()}@test.com", name="Snap")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    from datetime import date
    from decimal import Decimal

    trip = Trip(
        user_id=user.id,
        destination="Goa, India",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        budget_total=Decimal("40000.00"),
        currency="INR",
        group_size=2,
        pace="balanced",
    )
    db_session.add(trip)
    db_session.commit()
    db_session.refresh(trip)

    pool = _mock_pool()
    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.post(f"/trips/{trip.id}/plan")

    assert response.status_code == 202
    request_dict = pool.enqueue_job.call_args.args[2]
    assert request_dict["start_date"] == "2026-07-01"
    assert request_dict["end_date"] == "2026-07-03"
    assert request_dict["budget_total"] == 40000.0
