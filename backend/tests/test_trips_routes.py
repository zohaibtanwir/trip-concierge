"""Trip CRUD endpoints: POST /trips and GET /trips/{trip_id}.

Slice 3.2: POST /trips now requires auth and derives user_id from the
JWT. user_id is no longer accepted in the request body — the column
exists on the model but it's set server-side.

Slice 4.2 (trip-concierge-2th): GET /trips/{id} now requires auth +
ownership. The 404-when-missing test uses `authed_client` because an
unauthenticated caller short-circuits to 401 before the route-handler
runs. Cross-user 403 is covered separately in test_trip_ownership.py.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User


def test_post_then_get_trip_roundtrip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, user = authed_client

    payload = {
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
    # user_id is derived from the JWT, not the body, and surfaces on the read view.
    assert created["user_id"] == str(user.id)
    trip_id = created["id"]
    uuid.UUID(trip_id)  # raises if not a valid UUID

    get_resp = client.get(f"/trips/{trip_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == trip_id
    assert fetched["destination"] == "Goa"
    assert fetched["group_size"] == 2
    assert fetched["currency"] == "INR"


def test_post_trip_rejects_missing_destination(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    resp = client.post("/trips", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert any(err["loc"][-1] == "destination" for err in body["detail"])


def test_post_trip_returns_401_without_token(client: TestClient) -> None:
    """The auth gate is the load-bearing change in this slice.

    Without the JWT header the route must reject — otherwise any caller
    could create trips. The MCP server attaches the token; an unauth'd
    caller (curl, a misconfigured PWA dev build) sees 401.
    """
    resp = client.post(
        "/trips",
        json={"destination": "Goa"},
    )
    assert resp.status_code == 401


def test_post_trip_returns_401_with_bad_token(client: TestClient) -> None:
    resp = client.post(
        "/trips",
        json={"destination": "Goa"},
        headers={"x-tc-token": "not-a-valid-jwt"},
    )
    assert resp.status_code == 401


def test_post_trip_ignores_user_id_in_body(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Defense in depth: even if a client tries to spoof user_id by
    pasting it into the body, the JWT subject wins.

    Pydantic config `extra="ignore"` should drop the field silently;
    this test verifies that the created trip is owned by the JWT user,
    not the spoofed body user.
    """
    client, user = authed_client
    other_user = User(email=f"victim-{uuid.uuid4()}@test.com", name="Victim")
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    resp = client.post(
        "/trips",
        json={"destination": "Goa", "user_id": str(other_user.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == str(user.id), "body-supplied user_id must not override JWT subject"


def test_get_trip_returns_404_when_missing(
    authed_client: tuple[TestClient, User],
) -> None:
    """Authenticated request for a trip_id that doesn't exist returns 404.
    The 401 path (unauth) is covered above; the 403 path (cross-user) is
    covered in test_trip_ownership.py.
    """
    client, _ = authed_client
    resp = client.get(f"/trips/{uuid.uuid4()}")
    assert resp.status_code == 404
