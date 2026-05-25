"""Trip CRUD endpoints: POST /trips and GET /trips/{trip_id}."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User


def _make_user(db: Session, email: str = "alice@example.com") -> User:
    user = User(email=email, name="Alice")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_post_then_get_trip_roundtrip(client: TestClient, db_session: Session) -> None:
    user = _make_user(db_session)

    payload = {
        "user_id": str(user.id),
        "destination": "Goa",
        "start_date": "2026-07-01",
        "end_date": "2026-07-05",
        "group_size": 2,
        "budget_total": "40000.00",
        "currency": "INR",
        "pace": "balanced",
    }
    create_resp = client.post("/trips", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["destination"] == "Goa"
    assert created["status"] == "draft"
    trip_id = created["id"]
    uuid.UUID(trip_id)  # raises if not a valid UUID

    get_resp = client.get(f"/trips/{trip_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == trip_id
    assert fetched["destination"] == "Goa"
    assert fetched["group_size"] == 2
    assert fetched["currency"] == "INR"


def test_post_trip_rejects_missing_destination(client: TestClient, db_session: Session) -> None:
    user = _make_user(db_session)
    payload = {
        "user_id": str(user.id),
        # destination omitted on purpose
    }
    resp = client.post("/trips", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert any(err["loc"][-1] == "destination" for err in body["detail"])


def test_get_trip_returns_404_when_missing(client: TestClient) -> None:
    resp = client.get(f"/trips/{uuid.uuid4()}")
    assert resp.status_code == 404
