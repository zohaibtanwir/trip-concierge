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
    agent_summary: list | None = None,
) -> JobRun:
    """Insert a JobRun row directly for tests that exercise post-terminal state."""
    row = JobRun(
        job_id=job_id or uuid.uuid4().hex[:16],
        trip_id=trip_id,
        status=status,
        approved=approved,
        error=error,
        agent_summary=agent_summary if agent_summary is not None else [],
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


def test_status_surfaces_kind_from_json_active_job(client: TestClient, db_session: Session) -> None:
    """Slice 3.3 commit 3: PlanStatus gains an optional `kind` field. When
    the active_job key holds a JSON entry, `kind` surfaces in the response
    so the MCP get_trip tool can render "your refine is running" vs "your
    trip is being planned" without an extra HTTP call.
    """
    trip = _make_trip(db_session)
    active_payload = json.dumps({"job_id": "refine-1", "kind": "refine"}).encode()
    pool = _pool_with(active_job=active_payload)

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", _mock_job(JobStatus.in_progress)),
    ):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "running"
    assert body["job_id"] == "refine-1"
    assert body["kind"] == "refine"


def test_status_kind_defaults_to_plan_for_legacy_plain_string(
    client: TestClient, db_session: Session
) -> None:
    """Legacy plain-string entries in the active_job key collapse to
    kind='plan' — the same graceful-degradation rule as the route's
    legacy-tolerance helper.
    """
    trip = _make_trip(db_session)
    pool = _pool_with(active_job=b"job-legacy-1")

    with (
        patch("app.routes.plan.create_pool", return_value=pool),
        patch("app.routes.plan.Job", _mock_job(JobStatus.in_progress)),
    ):
        response = client.get(f"/trips/{trip.id}/plan/status")

    body = response.json()
    assert body["job_id"] == "job-legacy-1"
    assert body["kind"] == "plan"


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


# --- Slice 4.3 — agent_summary surfaces on terminal states ---


_SAMPLE_AGENT_SUMMARY = [
    {"agent": "Researcher", "step": 1, "duration_ms": 32500, "tokens": 1840},
    {"agent": "Local Expert", "step": 2, "duration_ms": 28100, "tokens": 1560},
    {"agent": "Logistics", "step": 3, "duration_ms": 41200, "tokens": 2310},
    {"agent": "Budget Auditor", "step": 4, "duration_ms": 18900, "tokens": 980},
]


def test_status_returns_agent_summary_when_done(client: TestClient, db_session: Session) -> None:
    """Slice 4.3 — PRD §F8 partial. The 'How this plan was made' panel reads
    PlanStatus.agent_summary; the route must surface JobRun.agent_summary
    on done state.
    """
    trip = _make_trip(db_session)
    _make_job_run(
        db_session,
        trip.id,
        status="succeeded",
        approved=True,
        agent_summary=_SAMPLE_AGENT_SUMMARY,
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "done"
    assert body["agent_summary"] == _SAMPLE_AGENT_SUMMARY


def test_status_returns_agent_summary_when_failed(client: TestClient, db_session: Session) -> None:
    """Even on failed state, agent_summary surfaces — partial activity is
    diagnostic ('Researcher ran for 32s, Local Expert never started')."""
    trip = _make_trip(db_session)
    partial = _SAMPLE_AGENT_SUMMARY[:2]  # only Researcher + Local Expert ran
    _make_job_run(
        db_session,
        trip.id,
        status="failed",
        approved=None,
        error="FatalJobError: planner output empty",
        agent_summary=partial,
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "failed"
    assert body["agent_summary"] == partial


def test_status_returns_empty_agent_summary_for_legacy_jobruns(
    client: TestClient, db_session: Session
) -> None:
    """JobRuns from pre-qek-a observability ran without step_callback wired,
    so their agent_summary column is `[]`. The route must surface empty list
    (not null), preserving downstream consumers' .map() / .length checks.
    """
    trip = _make_trip(db_session)
    _make_job_run(
        db_session,
        trip.id,
        status="succeeded",
        approved=True,
        agent_summary=[],
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "done"
    assert body["agent_summary"] == []


def test_status_returns_richest_agent_summary_when_multiple_jobruns(
    client: TestClient, db_session: Session
) -> None:
    """Hotfix 3x5 (option B+ richest-events-bias, 2026-06-08): when a trip
    has multiple terminal JobRuns (e.g., original plan_trip + later
    regenerate_day), the route must return the JobRun with the MOST
    agent_summary events — not just the latest.

    Regression motivator: Coorg trip had a rich plan_trip JobRun (11 events,
    Sat) displaced by a subsequent regenerate_day JobRun (1 event, Mon).
    PlanHistoryPanel rendered empty-state because the latest-by-time
    semantic picked the sparse regen. Richest-bias preserves demo visibility.
    """
    trip = _make_trip(db_session)
    # Original plan_trip — rich history (11 events).
    rich_summary = [
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:12:12Z", "elapsed_ms": 224413},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:13:33Z", "elapsed_ms": 305402},
        {"event": "task_completed", "task_index": 1, "elapsed_ms": 305402},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:15:27Z", "elapsed_ms": 419410},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:17:00Z", "elapsed_ms": 525000},
        {"event": "task_completed", "task_index": 2, "elapsed_ms": 525001},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:18:00Z", "elapsed_ms": 590000},
        {"event": "task_completed", "task_index": 3, "elapsed_ms": 590001},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:18:30Z", "elapsed_ms": 620000},
        {"event": "AgentFinish", "timestamp": "2026-06-06T16:18:58Z", "elapsed_ms": 630410},
        {"event": "callback_summary", "step_callback_count": 7, "task_callback_count": 3},
    ]
    _make_job_run(
        db_session,
        trip.id,
        status="succeeded",
        approved=True,
        agent_summary=rich_summary,
        job_id="job-original-plan",
    )
    # Later regenerate_day — sparse history (1 event), single-shot LLM
    # output produced no intermediate ReAct steps.
    sparse_summary = [
        {"event": "AgentFinish", "timestamp": "2026-06-08T19:40:26Z", "elapsed_ms": 21600},
    ]
    _make_job_run(
        db_session,
        trip.id,
        status="succeeded",
        approved=None,
        agent_summary=sparse_summary,
        job_id="job-later-regen",
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "done"
    # Load-bearing: the rich plan_trip summary wins despite NOT being the
    # latest by created_at. Richest-events-bias: ORDER BY
    # jsonb_array_length DESC NULLS LAST, created_at DESC.
    assert len(body["agent_summary"]) == 11, (
        f"expected 11-event rich summary; got {len(body['agent_summary'])}-event sparse"
    )
    assert body["agent_summary"] == rich_summary


def test_status_picks_latest_among_equal_richness(client: TestClient, db_session: Session) -> None:
    """Tiebreaker check: when two JobRuns have the same event count, the
    latest (by created_at) wins. Preserves the prior "latest" semantic for
    the common case where regens produce equal richness.
    """
    trip = _make_trip(db_session)
    summary_a = [{"event": "AgentFinish", "timestamp": "2026-06-06T16:12:12Z", "elapsed_ms": 1000}]
    summary_b = [{"event": "AgentFinish", "timestamp": "2026-06-08T19:40:26Z", "elapsed_ms": 2000}]
    _make_job_run(
        db_session, trip.id, status="succeeded", agent_summary=summary_a, job_id="job-earlier"
    )
    _make_job_run(
        db_session, trip.id, status="succeeded", agent_summary=summary_b, job_id="job-later"
    )
    pool = _pool_with()

    with patch("app.routes.plan.create_pool", return_value=pool):
        response = client.get(f"/trips/{trip.id}/plan/status")

    assert response.status_code == 200
    # Both have 1 event; latest-by-created_at wins as tiebreaker.
    assert response.json()["agent_summary"] == summary_b


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
