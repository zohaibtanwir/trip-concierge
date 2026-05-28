"""POST /trips/{trip_id}/refine — enqueue path tests.

Slice 3.3 commit 3. The route signature mirrors POST /plan from 2.5b:
load the trip, snapshot it into a request payload, check the active-job
Redis key, enqueue an arq job, write the active-job entry, return 202
with {job_id, status_url}.

Two differences from POST /plan:
- Auth-required (Depends(require_mcp_token)) — new routes adopt the
  slice-3.2 pattern; the older POST /plan staying unauthed is tracked
  for cleanup in a separate ticket.
- Active-job Redis value is JSON {"job_id": "...", "kind": "refine"}
  instead of a plain string. Tests assert the JSON payload landed.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User


def _make_trip(db: Session, user: User) -> Trip:
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


def _mock_pool(
    *, existing_active_job: bytes | None = None, job_id: str = "refine-xyz"
) -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    job = MagicMock()
    job.job_id = job_id
    pool.enqueue_job.return_value = job
    pool.setex.return_value = True
    return pool


def test_refine_returns_401_without_token(client: TestClient) -> None:
    resp = client.post(
        f"/trips/{uuid.uuid4()}/refine",
        json={"refinement_description": "make Day 2 chiller and less packed"},
    )
    assert resp.status_code == 401


def test_refine_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    pool = _mock_pool()
    with patch("app.routes.refine.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{uuid.uuid4()}/refine",
            json={"refinement_description": "make it cheaper and chiller"},
        )
    assert resp.status_code == 404
    assert not pool.enqueue_job.called


def test_refine_returns_422_for_empty_description(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()
    with patch("app.routes.refine.create_pool", return_value=pool):
        resp = client.post(f"/trips/{trip.id}/refine", json={"refinement_description": ""})
    assert resp.status_code == 422


def test_refine_returns_202_writes_json_active_job(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path: enqueue succeeds and the active_job Redis key contains
    JSON {"job_id":"...","kind":"refine"}. Load-bearing assertion: the
    value is JSON, not the plain job_id string.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool(job_id="refine-job-1")

    with patch("app.routes.refine.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/refine",
            json={"refinement_description": "make Day 2 chiller and add a beach day"},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "refine-job-1"
    assert body["status_url"] == f"/trips/{trip.id}/plan/status"

    # The arq task name is "refine_trip"; first arg is the trip_id.
    enqueue_args = pool.enqueue_job.call_args
    assert enqueue_args.args[0] == "refine_trip"
    assert enqueue_args.args[1] == str(trip.id)

    # Active-job key written with JSON value.
    setex_args = pool.setex.call_args
    assert setex_args.args[0] == f"trip:{trip.id}:active_job"
    assert setex_args.args[1] == 900  # TTL unchanged from 2.5b
    raw_value = setex_args.args[2]
    payload = json.loads(raw_value)
    assert payload == {"job_id": "refine-job-1", "kind": "refine"}


def test_refine_returns_409_when_another_job_in_flight(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Active-job key holds a JSON entry from a prior plan; refine refuses
    with a kind-aware 409 message. The conflicting kind surfaces in the
    detail so the LLM can render it correctly to the user.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    existing_payload = json.dumps({"job_id": "plan-job-old", "kind": "plan"}).encode()
    pool = _mock_pool(existing_active_job=existing_payload)

    with patch("app.routes.refine.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/refine",
            json={"refinement_description": "make it chill"},
        )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "planning" in detail, "kind label 'planning' (for kind='plan') must surface in 409"
    assert "plan-job-old" in detail
    assert not pool.enqueue_job.called
