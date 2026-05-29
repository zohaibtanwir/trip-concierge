"""GET /trips/{trip_id}/export?format=... — export endpoint tests.

Slice 3.5 commit 2. The route is auth-protected (owner-side data
download). Format is constrained to Literal["json","markdown"];
FastAPI enforces the enum at the type layer, producing 422 on any
other value.

Content-Type matrix pinned by tests 1 + 2:
- format=json     → application/json
- format=markdown → text/markdown; charset=utf-8

The charset=utf-8 is explicit so a future destination with non-
ASCII characters (₹ already; CJK foreseeable) renders cleanly in
any browser without protocol-layer encoding ambiguity.

Five cases:
1. Happy path JSON: 200 + application/json + body parses as JSON
2. Happy path Markdown: 200 + text/markdown; charset=utf-8 + body
   contains the destination heading
3. 401 without token (mirrors slice 3.3/3.4a auth gate pattern)
4. 404 when trip not found
5. 422 when format value isn't in the Literal (FastAPI auto-validation)
"""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.trip import Trip
from app.models.user import User


def _make_trip_with_block(db: Session, user: User) -> Trip:
    trip = Trip(
        user_id=user.id,
        destination="Goa, India",
        currency="INR",
        group_size=2,
        pace="balanced",
        status="succeeded",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    day = Day(trip_id=trip.id, day_number=1, summary="Anjuna day")
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


def test_export_json_returns_200_with_application_json_content_type(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Pins the JSON branch + Content-Type. A future refactor that
    changes the MIME type breaks this test deliberately.
    """
    client, user = authed_client
    trip = _make_trip_with_block(db_session, user)

    resp = client.get(f"/trips/{trip.id}/export?format=json")
    assert resp.status_code == 200, resp.text
    # FastAPI may append "; charset=utf-8" to application/json; allow either.
    assert resp.headers["content-type"].startswith("application/json")

    parsed = json.loads(resp.text)
    assert parsed["destination"] == "Goa, India"
    assert parsed["days"][0]["blocks"][0]["venue_name"] == "Anjuna Beach"


def test_export_markdown_returns_200_with_text_markdown_utf8_content_type(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Pins the Markdown branch + Content-Type. The explicit charset
    is what prevents browser-side encoding ambiguity for non-ASCII
    destinations (₹ already; CJK foreseeable).
    """
    client, user = authed_client
    trip = _make_trip_with_block(db_session, user)

    resp = client.get(f"/trips/{trip.id}/export?format=markdown")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8", (
        f"explicit charset=utf-8 required per slice 3.5 design; got "
        f"{resp.headers['content-type']!r}"
    )

    body = resp.text
    # Heading + venue surface so the user pastes a recognizable rendering.
    assert "# Goa, India" in body
    assert "Day 1" in body
    assert "Anjuna Beach" in body


def test_export_returns_401_without_token(client: TestClient) -> None:
    """The auth gate. /export is the OWNER-side download path
    (asymmetric with /shared which is intentionally unauth)."""
    resp = client.get(f"/trips/{uuid.uuid4()}/export?format=json")
    assert resp.status_code == 401


def test_export_returns_404_when_trip_not_found(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    resp = client.get(f"/trips/{uuid.uuid4()}/export?format=json")
    assert resp.status_code == 404
    assert "trip" in resp.json()["detail"].lower()


def test_export_returns_422_for_format_outside_literal_enum(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """FastAPI enforces Literal['json','markdown'] at the type layer.
    A request with format=pdf (v1.0b deferred, ticket trip-concierge-de6)
    or any other value returns 422 with FastAPI's structured validation
    error — no custom kind=structured-body path needed for v1.0a per the
    slice-3.4a discipline discussion (single rare error path).
    """
    client, user = authed_client
    trip = _make_trip_with_block(db_session, user)

    resp = client.get(f"/trips/{trip.id}/export?format=pdf")
    assert resp.status_code == 422
    # FastAPI's validation error body has a 'detail' list with field errors.
    body = resp.json()
    assert "detail" in body
