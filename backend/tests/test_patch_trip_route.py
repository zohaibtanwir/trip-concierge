"""PATCH /trips/{id} — settings-shaped column writes (slice 4.5b commit 1).

Per Q1=B sign-off: pace and budget_total are *settings* on the Trip
(column writes), not *rules* (append to constraints.rules[]). The
new PATCH route accepts {pace?, budget_total?}, updates the columns,
and enqueues a refine_trip job so the crew re-plans against the new
settings.

Six test scenarios pinned:
1. 401 without mcp token
2. 404 unknown trip
3. 422 invalid pace value (must be packed|balanced|lazy)
4. 422 empty body (at least one of pace/budget_total required)
5. 202 happy path — pace + budget_total written, refine enqueued,
   active_job kind='refine' (reuses same KIND_LABELS path as
   /constraints — refine is the underlying job, PATCH is UX)
6. 409 when a job is already in flight (active_job guard)
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User


def _make_trip(db: Session, user: User) -> Trip:
    trip = Trip(
        user_id=user.id,
        destination="Coorg",
        currency="INR",
        group_size=2,
        pace="balanced",
        budget_total=Decimal("30000.00"),
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def _mock_pool(
    *, existing_active_job: bytes | None = None, job_id: str = "patch-job-1"
) -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    job = MagicMock()
    job.job_id = job_id
    pool.enqueue_job.return_value = job
    pool.setex.return_value = True
    return pool


def test_patch_trip_returns_401_without_token(client: TestClient) -> None:
    resp = client.patch(
        f"/trips/{uuid.uuid4()}",
        json={"pace": "packed"},
    )
    assert resp.status_code == 401


def test_patch_trip_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    resp = client.patch(
        f"/trips/{uuid.uuid4()}",
        json={"pace": "packed"},
    )
    assert resp.status_code == 404


def test_patch_trip_returns_422_for_invalid_pace(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    client, user = authed_client
    trip = _make_trip(db_session, user)
    resp = client.patch(
        f"/trips/{trip.id}",
        json={"pace": "fast"},  # not in packed|balanced|lazy
    )
    assert resp.status_code == 422


def test_patch_trip_returns_422_for_empty_body(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """A PATCH with neither pace nor budget_total is a no-op call — reject
    at the schema layer (model_validator: at-least-one-of). Mirror of
    CreateTripInput's at-least-destination-or-vibe pattern."""
    client, user = authed_client
    trip = _make_trip(db_session, user)
    resp = client.patch(f"/trips/{trip.id}", json={})
    assert resp.status_code == 422


def test_patch_trip_returns_202_persists_settings_and_enqueues_refine(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path. Four load-bearing assertions:
    1. Trip.pace + Trip.budget_total columns are updated.
    2. arq enqueue called refine_trip with the synthesized settings-change
       description as args[2] — mentions both pace and budget_total.
    3. active_job key written as JSON with kind='refine' (reuses
       slice-3.3 KIND_LABELS path; PATCH is a UX abstraction over refine).
    4. The 202 body shape matches /constraints' (job_id + status_url).
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool(job_id="patch-job-x")

    with patch("app.routes.trip_settings.create_pool", return_value=pool):
        resp = client.patch(
            f"/trips/{trip.id}",
            json={"pace": "packed", "budget_total": 50000},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "patch-job-x"
    assert body["status_url"] == f"/trips/{trip.id}/plan/status"

    # arq task is "refine_trip" — reuses the refine worker.
    enqueue_args = pool.enqueue_job.call_args
    assert enqueue_args.args[0] == "refine_trip"
    assert enqueue_args.args[1] == str(trip.id)
    synthesized = enqueue_args.args[2]
    assert "pace" in synthesized.lower()
    assert "packed" in synthesized.lower()
    assert "budget" in synthesized.lower()
    assert "50000" in synthesized or "50,000" in synthesized

    # active_job key uses kind='refine'.
    setex_args = pool.setex.call_args
    assert setex_args.args[0] == f"trip:{trip.id}:active_job"
    payload = json.loads(setex_args.args[2])
    assert payload == {"job_id": "patch-job-x", "kind": "refine"}

    # Trip columns updated.
    db_session.refresh(trip)
    assert trip.pace == "packed"
    assert trip.budget_total == Decimal("50000")


def test_patch_trip_returns_409_when_job_in_flight(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """The active-job guard. A refine in flight blocks PATCH with the
    slice-3.3 'refinement' label from KIND_LABELS['refine']."""
    client, user = authed_client
    trip = _make_trip(db_session, user)
    existing_payload = json.dumps({"job_id": "refine-existing", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing_payload)

    with patch("app.routes.trip_settings.create_pool", return_value=pool):
        resp = client.patch(
            f"/trips/{trip.id}",
            json={"pace": "packed"},
        )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "refinement" in detail
    assert "refine-existing" in detail
    assert not pool.enqueue_job.called

    # Trip columns NOT updated on 409 — no write if we can't apply.
    db_session.refresh(trip)
    assert trip.pace == "balanced"  # original
