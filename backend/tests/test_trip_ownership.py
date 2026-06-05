"""Cross-user ownership tests for GET /trips/{id} + GET /trips/{id}/full.

Slice 4.2 / trip-concierge-2th. Before this slice:
- GET /trips/{id} had NO auth dependency at all (commented as "deferred to
  Phase 4 when PWA needs it").
- GET /trips/{id}/full had `_user: AuthedUser` declared but unused — the
  dependency forced 401 on missing tokens but never compared against
  Trip.user_id.

This slice closes both gaps. The tests pin the closures.

403 (not 404) on cross-user access: confirming existence to a non-owner
is a low-but-real information leak. A 404 lets an attacker probe trip_id
space to discover whether trips exist; a 403 returns the same response
whether the trip exists or not (well, only when the trip DOES exist —
404 is still the right answer for a genuinely missing trip_id). The
test below pins the 403 by giving a real trip owned by user B and
having user A request it.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


def _make_trip(db: Session, *, user_id: uuid.UUID) -> Trip:
    trip = Trip(
        user_id=user_id,
        destination="Goa, India",
        currency="INR",
        group_size=2,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def test_get_trip_403_on_cross_user_access(client: TestClient, db_session: Session) -> None:
    """User B creates a trip. User A presents a valid JWT and requests it.
    Response must be 403, not 200 (would leak the trip) and not 404
    (would imply the trip doesn't exist for a generic probe).

    The 403 happens AFTER auth succeeds — auth proves "you are user A",
    then ownership check proves "but this trip is user B's."
    """
    user_a = _make_user(db_session, label="a")
    user_b = _make_user(db_session, label="b")
    b_trip = _make_trip(db_session, user_id=user_b.id)

    token_a = issue_token(user_id=user_a.id, secret=_SECRET)
    with patch("app.routes.auth._secret", return_value=_SECRET):
        response = client.get(f"/trips/{b_trip.id}", headers={"x-tc-token": token_a})

    assert response.status_code == 403, (
        f"cross-user GET /trips/{{id}} must return 403. got: "
        f"{response.status_code}. body: {response.text}"
    )


def test_get_trip_full_403_on_cross_user_access(client: TestClient, db_session: Session) -> None:
    """Same shape as the /trips/{id} test but for /trips/{id}/full.

    Both endpoints leak trip ownership and content if ownership isn't
    enforced; the /full path leaks more (whole days→blocks→sources tree),
    so the closure here is structurally identical and equally load-bearing.
    """
    user_a = _make_user(db_session, label="a")
    user_b = _make_user(db_session, label="b")
    b_trip = _make_trip(db_session, user_id=user_b.id)

    token_a = issue_token(user_id=user_a.id, secret=_SECRET)
    with patch("app.routes.auth._secret", return_value=_SECRET):
        response = client.get(f"/trips/{b_trip.id}/full", headers={"x-tc-token": token_a})

    assert response.status_code == 403, (
        f"cross-user GET /trips/{{id}}/full must return 403. got: "
        f"{response.status_code}. body: {response.text}"
    )
