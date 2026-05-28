"""POST /trips/{trip_id}/days/{day_number}/regenerate — enqueue path.

Slice 3.3 commit 3. Same shape as POST /refine: auth-required, snapshot,
active-job check, enqueue, write JSON active_job, return 202.

Day-number validation: 1 ≤ day_number ≤ 30 (matches RegenerateDayInput's
Pydantic constraint). 422 on out-of-range. Further "does this trip
actually have a Day N?" check is the worker's job — the route just
enqueues.
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


def _mock_pool(*, existing_active_job: bytes | None = None, job_id: str = "regen-xyz") -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    job = MagicMock()
    job.job_id = job_id
    pool.enqueue_job.return_value = job
    pool.setex.return_value = True
    return pool


def test_regen_returns_401_without_token(client: TestClient) -> None:
    resp = client.post(f"/trips/{uuid.uuid4()}/days/1/regenerate", json={})
    assert resp.status_code == 401


def test_regen_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    pool = _mock_pool()
    with patch("app.routes.regenerate.create_pool", return_value=pool):
        resp = client.post(f"/trips/{uuid.uuid4()}/days/1/regenerate", json={})
    assert resp.status_code == 404
    assert not pool.enqueue_job.called


def test_regen_returns_422_for_day_number_zero(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """day_number must be >= 1. FastAPI's path parameter validation refuses
    0 because of the route's Path(ge=1) constraint.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()
    with patch("app.routes.regenerate.create_pool", return_value=pool):
        resp = client.post(f"/trips/{trip.id}/days/0/regenerate", json={})
    assert resp.status_code == 422
    assert not pool.enqueue_job.called


def test_regen_returns_202_writes_json_active_job(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path. Active-job Redis value is JSON with kind='regen'."""
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool(job_id="regen-job-1")

    with patch("app.routes.regenerate.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/days/2/regenerate",
            json={"hint": "more food, less hiking"},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "regen-job-1"

    # arq task name + args.
    enqueue_args = pool.enqueue_job.call_args
    assert enqueue_args.args[0] == "regenerate_day"
    assert enqueue_args.args[1] == str(trip.id)
    # day_number is the third positional arg.
    assert enqueue_args.args[2] == 2

    # Active-job JSON.
    setex_args = pool.setex.call_args
    assert setex_args.args[0] == f"trip:{trip.id}:active_job"
    payload = json.loads(setex_args.args[2])
    assert payload == {"job_id": "regen-job-1", "kind": "regen"}


def test_regen_returns_409_when_another_job_in_flight(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """An in-flight refine prevents a regen on the same trip. 409 names
    the conflicting kind as 'refinement' (human-readable label for 'refine').
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    existing_payload = json.dumps({"job_id": "refine-job-old", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing_payload)

    with patch("app.routes.regenerate.create_pool", return_value=pool):
        resp = client.post(f"/trips/{trip.id}/days/1/regenerate", json={})

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "refinement" in detail
    assert "refine-job-old" in detail
    assert not pool.enqueue_job.called
