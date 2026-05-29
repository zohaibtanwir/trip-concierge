"""GET /shared/{trip_id} — unauthenticated viewer endpoint.

Slice 3.5 commit 2. The route is INTENTIONALLY without an auth
dependency. The v1.0a privacy model is share-by-URL:

  Anyone with the trip_id (UUIDv4 = 128 bits of entropy) can view
  the trip, no sign-in or token required. Trip data carries no PII
  beyond destination + travel preferences; UUID guessability bounds
  the attack surface.

This file pins TWO load-bearing properties so a future "let's add
auth" change has to break a test deliberately:
1. The route returns 200 when called WITHOUT a token.
2. The route returns 200 when called with a token (auth is neither
   required nor rejected — auth is just irrelevant here).

Revocable tokens are deferred to ticket trip-concierge-gid (P3,
v1.0b) — flagged in the route docstring + inline route comment.

Four cases:
1. Happy path with token → 200 + TripFullRead shape
2. No token → 200 (pins the privacy model)
3. 404 when trip not found
4. State-not-gated: trip in status="draft" with zero days still
   returns 200 with its data — state-gate is at the MCP-tool layer,
   not the endpoint
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.trip import Trip
from app.models.user import User


def _make_trip(
    db: Session,
    user: User,
    *,
    with_blocks: bool = True,
    status: str = "succeeded",
) -> Trip:
    trip = Trip(
        user_id=user.id,
        destination="Goa, India",
        currency="INR",
        group_size=2,
        pace="balanced",
        status=status,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    if with_blocks:
        day = Day(trip_id=trip.id, day_number=1, summary="Day 1")
        db.add(day)
        db.commit()
        db.refresh(day)

        block = Block(
            day_id=day.id,
            order=1,
            type="venue",
            venue_name="Anjuna Beach",
            start_time="09:00",
            duration_minutes=120,
            currency="INR",
        )
        db.add(block)
        db.commit()

    return trip


def test_shared_happy_path_returns_200_with_trip_full_read_shape(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path WITH a token — proves auth is just irrelevant (not
    rejected and not required). Together with the no-token test below,
    pins that the route is auth-agnostic.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)

    resp = client.get(f"/shared/{trip.id}")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["id"] == str(trip.id)
    assert body["destination"] == "Goa, India"
    assert body["currency"] == "INR"
    assert len(body["days"]) == 1
    assert body["days"][0]["blocks"][0]["venue_name"] == "Anjuna Beach"


def test_shared_route_returns_200_without_any_auth_token_v1_0a_privacy_model(
    client: TestClient,
    db_session: Session,
) -> None:
    """The load-bearing privacy-model pin. A future contributor who
    "fixes" /shared by adding require_mcp_token MUST break this test
    deliberately. The v1.0a design is intentional: share-by-URL,
    128-bit UUID entropy bounds the attack surface, no PII beyond
    destination + travel preferences.

    Revocable tokens are tracked as trip-concierge-gid (P3) for v1.0b.
    Until that ships, /shared is intentionally token-less.
    """
    # Build the trip via a transient user — we don't need authed_client.
    user = User(email=f"shared-{uuid.uuid4()}@test.com", name="Shared Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    trip = _make_trip(db_session, user)

    # `client` fixture has NO x-tc-token header.
    resp = client.get(f"/shared/{trip.id}")
    assert resp.status_code == 200, (
        "unauth GET /shared/{id} must return 200 per v1.0a privacy model. "
        "If you're seeing 401, someone added require_mcp_token to the "
        "route — that's a deliberate design break, see ticket "
        "trip-concierge-gid for the v1.0b upgrade path."
    )
    assert resp.json()["destination"] == "Goa, India"


def test_shared_returns_404_when_trip_does_not_exist(client: TestClient) -> None:
    resp = client.get(f"/shared/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert "trip" in resp.json()["detail"].lower()


def test_shared_state_not_gated_returns_200_for_draft_trip_with_zero_days(
    client: TestClient,
    db_session: Session,
) -> None:
    """A draft-status trip with zero days should return 200, NOT 409
    or a clarification body. State-gate enforcement is at the MCP-tool
    layer (slice 3.5 commit 3); the unauth endpoint stays a pure data
    surface.

    Future consumers (a Phase 4 PWA) can render their own
    "still planning" UI from the empty data, OR call /plan/status
    in parallel — the endpoint doesn't impose a state model.
    """
    user = User(email=f"draft-{uuid.uuid4()}@test.com", name="Draft Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    trip = _make_trip(db_session, user, with_blocks=False, status="draft")

    resp = client.get(f"/shared/{trip.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "draft"
    assert body["days"] == []
