"""GET /trips/{id}/plan/status and DELETE /trips/{id}/plan — Slice 2.5c.

State resolution order (route logic under test):
1. Redis `trip:{id}:cancelling` present → state="cancelling"
2. Redis `trip:{id}:active_job` present → arq Job.status() decides
       JobStatus.queued    → state="queued"
       JobStatus.in_progress → state="running" (+ optional progress_message)
3. Else: latest JobRun row for trip → state in {done|failed|cancelled}
       (`approved` populated only for state="done")
4. Else: 404

Tests patch `app.routes.plan.create_pool` (route's Redis pool factory) and
`app.routes.plan.Job` (route's arq Job class) — same pattern as
test_plan_endpoint.py. The `pool.get.called` / `Job` patch presence asserts
are the load-bearing guard against patch-path drift: if the wrong path is
patched, the route hits real Redis (which the CI redis container makes
succeed), and the test silently passes against the wrong code.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.jobs import JobStatus
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.models.trip import Trip
from app.models.user import User


def _make_trip(db: Session) -> Trip:
    user = User(email=f"status-{uuid.uuid4()}@test.com", name="Status Test")
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


def _make_job_run(
    db: Session,
    trip_id: uuid.UUID,
    *,
    status: str,
    approved: bool | None = None,
    error: str | None = None,
    job_id: str | None = None,
) -> JobRun:
    """Insert a JobRun row directly for tests that exercise post-terminal state."""
    row = JobRun(
        job_id=job_id or uuid.uuid4().hex[:16],
        trip_id=trip_id,
        status=status,
        approved=approved,
        error=error,
        agent_summary=[],
        total_tokens=0,
        total_cost=Decimal("0"),
        total_duration_ms=0,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _pool_with(
    *,
    cancelling: bytes | None = None,
    active_job: bytes | None = None,
    progress: bytes | None = None,
) -> AsyncMock:
    """AsyncMock pool whose `.get` returns per-key fixtures by key suffix.

    We match by suffix so the test doesn't need to know the trip_id to set
    up the mock. The route always uses `trip:{id}:<suffix>`.
    """
    pool = AsyncMock()
    by_suffix: dict[str, bytes | None] = {
        "cancelling": cancelling,
        "active_job": active_job,
        "progress": progress,
    }

    async def fake_get(key: str | bytes) -> bytes | None:
        k = key.decode() if isinstance(key, bytes) else key
        for suffix, value in by_suffix.items():
            if k.endswith(":" + suffix):
                return value
        return None

    pool.get.side_effect = fake_get
    pool.delete.return_value = 1
    pool.setex.return_value = True
    return pool


def _mock_job_factory_with_abort() -> tuple[MagicMock, AsyncMock]:
    """Mock that stands in for `arq.jobs.Job`. Returns (factory, abort_mock).

    Caller uses `patch("app.routes.plan.Job", factory)` and asserts on
    `abort_mock.assert_awaited_once()` to verify the cancel path hit it.
    """
    instance = MagicMock()
    abort_mock = AsyncMock(return_value=True)
    instance.abort = abort_mock
    factory = MagicMock(return_value=instance)
    return factory, abort_mock


def _mock_job(status_value: JobStatus) -> MagicMock:
    """Factory mock returned in place of arq.jobs.Job(...). `.status()` is async."""
    job_factory = MagicMock()
    instance = MagicMock()
    instance.status = AsyncMock(return_value=status_value)
    job_factory.return_value = instance
    return job_factory


# ---------------------------------------------------------------------------
# GET /trips/{id}/plan/status
# ---------------------------------------------------------------------------


def test_status_returns_404_when_no_history(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    pool = _pool_with()  # nothing in redis, no JobRun rows

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 404
    assert pool.get.called, "pool.get was not called — patch target for create_pool may be wrong"


def test_status_returns_queued_when_arq_job_queued(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    pool = _pool_with(active_job=b"job-q-1")

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", _mock_job(JobStatus.queued)),
    ):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "queued"
    assert body["job_id"] == "job-q-1"
    assert body["approved"] is None
    assert body["progress_message"] is None
    assert body["error"] is None


def test_status_returns_running_with_progress(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    progress_payload = json.dumps(
        {"agent": "Researcher", "pass": 1, "message": "Searching Goa venues"}
    ).encode()
    pool = _pool_with(active_job=b"job-r-1", progress=progress_payload)

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", _mock_job(JobStatus.in_progress)),
    ):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "running"
    assert body["progress_message"] == {
        "agent": "Researcher",
        "pass": 1,
        "message": "Searching Goa venues",
    }


@pytest.mark.parametrize("approved", [True, False])
def test_status_returns_done_with_approved_value(
    client: TestClient, db_session: Session, approved: bool
) -> None:
    """state='done' is lifecycle; approved=True|False is the outcome.

    True path: crew ran cleanly and the Auditor approved the plan.
    False path: crew ran cleanly but Auditor returned approved=false
    (infeasible-plan signal). Client branches on approved AFTER seeing done.
    """
    trip = _make_trip(db_session)
    _make_job_run(db_session, trip.id, status="succeeded", approved=approved)
    pool = _pool_with()  # nothing in redis — terminal state lives in JobRun

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "done"
    assert body["approved"] is approved
    assert body["error"] is None


def test_status_returns_failed(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    _make_job_run(
        db_session,
        trip.id,
        status="failed",
        approved=None,
        error="FatalJobError: unparseable auditor output",
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "failed"
    assert body["approved"] is None
    assert "FatalJobError" in body["error"]


def test_status_returns_cancelled(client: TestClient, db_session: Session) -> None:
    trip = _make_trip(db_session)
    _make_job_run(db_session, trip.id, status="cancelled", approved=None, error="cancelled by user")
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "cancelled"
    assert body["approved"] is None


def test_status_returns_cancelling_during_tombstone_race(
    client: TestClient, db_session: Session
) -> None:
    """Race: DELETE has set the `cancelling` tombstone and called abort_job, but
    the worker hasn't yet written the JobRun row. GET must NOT return 404 in
    that window — it returns state='cancelling' so the client keeps polling.
    """
    trip = _make_trip(db_session)
    # Tombstone present, active_job still present (worker hasn't cleaned up),
    # no JobRun row yet (worker hasn't written it).
    pool = _pool_with(cancelling=b"1", active_job=b"job-c-1")

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        # Even if arq still reports the job as in_progress, the tombstone wins.
        patch("app.routes.plan.Job", _mock_job(JobStatus.in_progress)),
    ):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "cancelling"
    assert body["approved"] is None


# ---------------------------------------------------------------------------
# DELETE /trips/{id}/plan
# ---------------------------------------------------------------------------


def test_delete_returns_204_and_sets_cancelling_tombstone(
    client: TestClient, db_session: Session
) -> None:
    trip = _make_trip(db_session)
    pool = _pool_with(active_job=b"job-del-1")
    job_factory, abort_mock = _mock_job_factory_with_abort()

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", job_factory),
    ):
        response = client.delete(f"/trips/{trip.id}/plan")

    assert response.status_code == 204
    # Tombstone must be set BEFORE abort — race-free for the GET handler.
    setex_call = pool.setex.call_args
    assert setex_call is not None, "cancelling tombstone was not written"
    assert setex_call.args[0] == f"trip:{trip.id}:cancelling"
    assert setex_call.args[1] == 30  # 30s TTL per refinement #2
    # Job(...).abort() was called for the live job_id
    job_factory.assert_called_once()
    assert job_factory.call_args.args[0] == "job-del-1", (
        "Job factory was not constructed with the active job_id"
    )
    abort_mock.assert_awaited_once()
    # active_job key cleared
    pool.delete.assert_any_call(f"trip:{trip.id}:active_job")


def test_delete_returns_404_when_no_active_and_no_jobrun(
    client: TestClient, db_session: Session
) -> None:
    trip = _make_trip(db_session)
    pool = _pool_with()  # no active_job, no JobRun
    job_factory, abort_mock = _mock_job_factory_with_abort()

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", job_factory),
    ):
        response = client.delete(f"/trips/{trip.id}/plan")

    assert response.status_code == 404
    assert not abort_mock.called, "shouldn't abort when there's nothing in flight"


def test_delete_returns_409_when_jobrun_already_terminal(
    client: TestClient, db_session: Session
) -> None:
    """A completed (or failed, or cancelled) job can't be cancelled.

    409 — distinct from 404 — tells the client the job ran to completion;
    they should call GET /status to read the outcome.
    """
    trip = _make_trip(db_session)
    _make_job_run(db_session, trip.id, status="succeeded", approved=True)
    pool = _pool_with()  # no active_job (already terminal)
    job_factory, abort_mock = _mock_job_factory_with_abort()

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", job_factory),
    ):
        response = client.delete(f"/trips/{trip.id}/plan")

    assert response.status_code == 409
    assert not abort_mock.called


def test_delete_is_idempotent_during_cancelling_window(
    client: TestClient, db_session: Session
) -> None:
    """Second DELETE while the cancelling tombstone is still present.

    The first DELETE deleted the active_job key and set the tombstone. The
    worker hasn't finished writing the JobRun yet. A retry of DELETE should
    return 204 without re-aborting (no active_job to abort).
    """
    trip = _make_trip(db_session)
    pool = _pool_with(cancelling=b"1", active_job=None)  # active gone, tombstone present
    job_factory, abort_mock = _mock_job_factory_with_abort()

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", job_factory),
    ):
        response = client.delete(f"/trips/{trip.id}/plan")

    assert response.status_code == 204
    assert not abort_mock.called, "no active_job to abort on the retry — abort must not fire"
