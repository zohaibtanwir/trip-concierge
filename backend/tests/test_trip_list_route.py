"""GET /trips — list endpoint tests (slice 4.2 / trip-concierge-2th).

Eleven tests pin the contract:

1.   **Ownership isolation** — caller only sees their own trips.
2-4. **Terminal-state mapping** — JobRun.status → list-page state:
       succeeded → 'succeeded'
       failed    → 'failed'
       cancelled → 'failed'  (cancelled is a failed UX, not a separate state)
5.   **Planning overlay** — Redis active_job key promotes a no-JobRun trip
       to state='planning'.
6.   **no_job state** — no JobRun(kind='plan') AND no Redis active_job.
7.   **Non-plan filter** — refine/regen JobRuns must not influence the
       terminal state. Pins the WHERE kind='plan' clause in the LATERAL JOIN.
8.   **Refine-doesn't-mask-success** — a succeeded plan + active refine
       in Redis stays 'succeeded'; the Redis overlay only fires when SQL
       said 'no_job'.
9.   **Graceful degradation** — Redis failure → no_job (not 500).

Plus the 2 ownership tests in test_trip_ownership.py = 11 total for
commit 1.

Per CLAUDE.md (slice 4.1's adapter-write gap Marsh pattern): these are
integration tests against a real Postgres test DB, not unit tests with
SQLAlchemy mocked. The LATERAL JOIN + Redis MGET merge is the load-
bearing surface; testing it against the actual query planner is the
only way to catch a mis-specified JOIN. Redis is mocked because the
test goal is the merge logic, not Redis itself.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.job_run import JobRun
from app.models.trip import Trip
from app.models.user import User
from app.services.mcp_tokens import issue_token

_SECRET = "dev-test-secret-32-bytes-or-more-x"


def _make_user(db: Session, *, label: str) -> User:
    user = User(email=f"{label}-{uuid.uuid4()}@test.com", name=f"User {label}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_trip(db: Session, *, user_id: uuid.UUID, destination: str = "Goa, India") -> Trip:
    trip = Trip(
        user_id=user_id,
        destination=destination,
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
    *,
    trip_id: uuid.UUID,
    status: str,
    kind: str = "plan",
    job_id: str | None = None,
) -> JobRun:
    row = JobRun(
        job_id=job_id or uuid.uuid4().hex,
        trip_id=trip_id,
        kind=kind,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _mock_redis_pool(
    *,
    mget_returns: list | None = None,
    mget_raises: Exception | None = None,
) -> AsyncMock:
    """Build an AsyncMock that stands in for arq.create_pool's return value.

    mget_returns is what pool.mget(keys) yields. Default: empty list, which
    only works when no_job_trip_ids is empty (no MGET is issued). For tests
    that DO seed no-JobRun trips, pass mget_returns matching the order of
    no_job_trip_ids the service builds (sorted by Trip.created_at DESC).

    mget_raises (if set) makes pool.mget() raise — exercises the graceful-
    degradation path in _planning_trip_ids.
    """
    pool = AsyncMock()
    if mget_raises is not None:
        pool.mget.side_effect = mget_raises
    else:
        pool.mget.return_value = mget_returns or []
    return pool


def _call_list(client: TestClient, token: str, pool: AsyncMock):
    """GET /trips with auth + create_pool both patched."""
    with (
        patch("app.routes.auth._secret", return_value=_SECRET),
        patch("app.services.trip_service.create_pool", return_value=pool),
    ):
        return client.get("/trips", headers={"x-tc-token": token})


def test_list_trips_only_returns_callers_trips(client: TestClient, db_session: Session) -> None:
    """Two users, each with their own trips. Caller (User A) sees their two
    trips; User B's single trip is invisible. Pins the WHERE user_id filter
    — the highest-risk single line in the list query.
    """
    user_a = _make_user(db_session, label="a")
    user_b = _make_user(db_session, label="b")

    a_trip_1 = _make_trip(db_session, user_id=user_a.id, destination="Goa, India")
    a_trip_2 = _make_trip(db_session, user_id=user_a.id, destination="Coorg, India")
    _make_trip(db_session, user_id=user_b.id, destination="Pondicherry, India")

    token = issue_token(user_id=user_a.id, secret=_SECRET)
    # Both of A's trips have no JobRun → both land in no_job_trip_ids → one
    # MGET fires returning [None, None] (no active jobs).
    pool = _mock_redis_pool(mget_returns=[None, None])
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    returned_ids = {item["id"] for item in items}
    assert returned_ids == {str(a_trip_1.id), str(a_trip_2.id)}, (
        f"caller A should see exactly their two trips, not user B's. returned: {returned_ids}"
    )


def test_list_trips_succeeded_state_when_latest_plan_jobrun_succeeded(
    client: TestClient, db_session: Session
) -> None:
    user = _make_user(db_session, label="succ")
    trip = _make_trip(db_session, user_id=user.id)
    _make_job_run(db_session, trip_id=trip.id, status="succeeded", kind="plan")

    token = issue_token(user_id=user.id, secret=_SECRET)
    # Terminal state from SQL → no Redis MGET issued. Pool's mget stays unused.
    pool = _mock_redis_pool()
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "succeeded", (
        f"latest JobRun status='succeeded' must derive state='succeeded'. "
        f"got: {items[0]['state']!r}"
    )
    # Confirm we did NOT issue a needless Redis call when SQL gave terminal state.
    assert not pool.mget.called, (
        "MGET should not fire when no trips are in no_job state — that's the "
        "narrowing optimization in list_trips_for_user."
    )


def test_list_trips_failed_state_when_latest_plan_jobrun_failed(
    client: TestClient, db_session: Session
) -> None:
    user = _make_user(db_session, label="fail")
    trip = _make_trip(db_session, user_id=user.id)
    _make_job_run(db_session, trip_id=trip.id, status="failed", kind="plan")

    token = issue_token(user_id=user.id, secret=_SECRET)
    pool = _mock_redis_pool()
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "failed", (
        f"latest JobRun status='failed' must derive state='failed'. got: {items[0]['state']!r}"
    )


def test_list_trips_failed_state_when_latest_plan_jobrun_cancelled(
    client: TestClient, db_session: Session
) -> None:
    """Cancelled jobs render as 'failed' in the list UX. The detail page
    can disambiguate via the JobRun.error field; the list page does not.

    Pins the (failed, cancelled) → 'failed' collapse in the derived-state
    CASE statement. A refactor that drops cancelled from the failed branch
    would cause cancelled trips to render as no_job — confusing UX.
    """
    user = _make_user(db_session, label="canc")
    trip = _make_trip(db_session, user_id=user.id)
    _make_job_run(db_session, trip_id=trip.id, status="cancelled", kind="plan")

    token = issue_token(user_id=user.id, secret=_SECRET)
    pool = _mock_redis_pool()
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "failed", (
        f"latest JobRun status='cancelled' must derive state='failed' "
        f"(cancelled and failed both surface as failed UX). "
        f"got: {items[0]['state']!r}"
    )


def test_list_trips_planning_state_when_active_job_in_redis(
    client: TestClient, db_session: Session
) -> None:
    """Trip with no JobRun row but a Redis active_job key present →
    state='planning'. This is the load-bearing UX correctness test for
    the dual-read pattern.

    Without this overlay, a just-submitted trip (Postgres has no JobRun
    yet because the worker hasn't reached its terminal write) would
    render as 'Not started' in the list — confusing UX leading the user
    to think their trip didn't kick off or to hit a hypothetical "Plan
    Again" on a job actually running.
    """
    user = _make_user(db_session, label="plan")
    planning_trip = _make_trip(db_session, user_id=user.id, destination="Coorg, India")
    idle_trip = _make_trip(db_session, user_id=user.id, destination="Goa, India")
    # Note: list query orders DESC by created_at. idle_trip was created
    # AFTER planning_trip, so MGET keys are: [idle_trip, planning_trip].

    token = issue_token(user_id=user.id, secret=_SECRET)
    # Order matches the no_job_trip_ids order built by the service (DESC).
    # First element corresponds to idle_trip (no active job), second to
    # planning_trip (active job present, value is the JSON encode_active_value
    # output from routes/plan.py but for the helper any non-None counts).
    pool = _mock_redis_pool(mget_returns=[None, b'{"job_id":"running-xyz","kind":"plan"}'])
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 2

    by_id = {item["id"]: item for item in items}
    assert by_id[str(planning_trip.id)]["state"] == "planning", (
        f"trip with Redis active_job key must derive state='planning'. "
        f"got: {by_id[str(planning_trip.id)]['state']!r}"
    )
    assert by_id[str(idle_trip.id)]["state"] == "no_job", (
        f"trip with no Redis active_job key must stay 'no_job'. "
        f"got: {by_id[str(idle_trip.id)]['state']!r}"
    )


def test_list_trips_no_job_state_when_no_plan_jobrun_exists(
    client: TestClient, db_session: Session
) -> None:
    """Trip with no JobRun row AND no Redis active_job → state='no_job'.
    Pins the LEFT JOIN LATERAL behavior — a missing row must not drop
    the trip from the result (would happen with INNER JOIN) and must
    not error.
    """
    user = _make_user(db_session, label="nojob")
    trip = _make_trip(db_session, user_id=user.id)

    token = issue_token(user_id=user.id, secret=_SECRET)
    pool = _mock_redis_pool(mget_returns=[None])
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1, (
        "trip without a JobRun must still appear in the list (LEFT JOIN, "
        "not INNER JOIN). this is a navigational surface, not a filter."
    )
    assert items[0]["id"] == str(trip.id)
    assert items[0]["state"] == "no_job", (
        f"no JobRun(kind='plan') row AND no Redis active_job → "
        f"state must be 'no_job'. got: {items[0]['state']!r}"
    )


def test_list_trips_derived_state_ignores_non_plan_jobruns(
    client: TestClient, db_session: Session
) -> None:
    """Trip with a succeeded plan JobRun followed by a failed refine JobRun
    must derive state='succeeded' — refine and regen JobRuns do not
    influence the list-page state. Pins the WHERE kind='plan' filter in
    the LATERAL subquery.

    Without this filter, the most recent JobRun (a failed refine) would
    win, causing a user-visible regression: the list would mark a
    succeeded trip as failed simply because the user tried (and failed)
    to refine it. This is the highest-cost-to-discover bug in the
    derived-state surface.
    """
    user = _make_user(db_session, label="filter")
    trip = _make_trip(db_session, user_id=user.id)
    # Original plan succeeded.
    _make_job_run(db_session, trip_id=trip.id, status="succeeded", kind="plan")
    # Later refine attempt failed — must be ignored by the list query.
    _make_job_run(db_session, trip_id=trip.id, status="failed", kind="refine")

    token = issue_token(user_id=user.id, secret=_SECRET)
    pool = _mock_redis_pool()
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "succeeded", (
        f"non-plan JobRuns (refine, regen) must not influence list state. "
        f"trip had succeeded plan + failed refine; expected state='succeeded' "
        f"(the trip itself is succeeded; the failed refine is the user's "
        f"problem with the detail page, not the list). got: {items[0]['state']!r}"
    )


def test_list_trips_keeps_succeeded_state_when_refine_active_in_redis(
    client: TestClient, db_session: Session
) -> None:
    """A succeeded trip with an active refine in Redis stays 'succeeded'
    — the planning overlay applies ONLY when SQL said 'no_job'. This
    pins the policy that 'planning' = plan job in flight, not "any job
    in flight."

    A succeeded trip with an active refine still has a valid plan; the
    refine is a separate operation whose progress lives on the detail
    page. Promoting the list state to 'planning' would hide the
    succeeded plan from the user behind a misleading badge.

    This test also confirms the narrowing optimization: even though
    there's a Redis active_job for this trip, the service never calls
    MGET because no_job_trip_ids is empty (the SQL gave a terminal
    state, no overlay needed).
    """
    user = _make_user(db_session, label="refine-active")
    trip = _make_trip(db_session, user_id=user.id)
    _make_job_run(db_session, trip_id=trip.id, status="succeeded", kind="plan")
    # If a Redis active_job key existed, the narrowing optimization
    # means MGET wouldn't even be issued for this trip — so even though
    # we'd seed it conceptually, it's never read. Mock the pool to
    # return one value if MGET is wrongly called (the assertion below
    # catches the bug).
    token = issue_token(user_id=user.id, secret=_SECRET)
    pool = _mock_redis_pool(mget_returns=[b'{"job_id":"refine-1","kind":"refine"}'])
    response = _call_list(client, token, pool)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "succeeded", (
        f"succeeded trip with active refine must stay 'succeeded'. got: {items[0]['state']!r}"
    )
    assert not pool.mget.called, (
        "MGET must not fire when no trips are in no_job state — the narrowing "
        "optimization is what enforces the policy that planning overlay "
        "applies only to no-JobRun trips."
    )


def test_list_trips_degrades_to_no_job_on_redis_error(
    client: TestClient, db_session: Session
) -> None:
    """Redis MGET failure must not 500 the list endpoint. Trips with no
    JobRun fall back to state='no_job' (same as if Redis were never
    consulted). This is the graceful-degradation contract documented in
    _planning_trip_ids and list_trips_for_user.

    Without this contract, a Redis outage would take down the trip list
    page entirely — a high-blast-radius failure mode for a transient
    dependency. The trade-off: during Redis outage, in-flight planning
    trips render as 'no_job' until Redis recovers. That's a temporary
    UX degradation, not a system failure.
    """
    user = _make_user(db_session, label="redis-down")
    trip = _make_trip(db_session, user_id=user.id)

    token = issue_token(user_id=user.id, secret=_SECRET)
    # Simulate Redis connection failure during the MGET.
    pool = _mock_redis_pool(mget_raises=ConnectionError("redis unreachable"))
    response = _call_list(client, token, pool)

    assert response.status_code == 200, (
        f"Redis failure must not 500 the list. got: {response.status_code}. body: {response.text}"
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(trip.id)
    assert items[0]["state"] == "no_job", (
        f"on Redis failure, no-JobRun trips fall back to 'no_job' "
        f"(not 'planning', not error). got: {items[0]['state']!r}"
    )
