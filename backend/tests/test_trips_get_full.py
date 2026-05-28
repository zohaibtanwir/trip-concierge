"""GET /trips/{id}/full — read endpoint that returns the trip plus all its
days, blocks, and sources in a single JSON tree.

Scope choice (slice 3.3 commit 2): this endpoint does NOT include plan_status.
The MCP get_trip tool composes /full with /plan/status (existing from 2.5c)
itself — two HTTP calls per tool invocation, matching the create_trip
two-call pattern from 3.2. That keeps this commit a pure additive read
endpoint with no refactor of plan.py.

Auth: same require_mcp_token gate as POST /trips. Slice 3.3 keeps the
"any authenticated user can read any trip" posture from earlier slices;
ownership-locked reads land in Phase 4 alongside the PWA.

Test cases:
- 401 without auth (the gate fires before route logic)
- 404 with valid auth but unknown trip_id
- 200 with empty days (trip created, planning never started — the
  partial-failure path from 3.2)
- 200 with a full hierarchy: 2 days, 3 blocks each, 1 source per block
  → response renders the tree with blocks ordered by `order` and sources
  nested under their blocks
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User


def _make_full_trip(db: Session, user_id: uuid.UUID) -> Trip:
    """Seed a trip with 2 days, 3 blocks per day, 1 source per block.

    Blocks intentionally inserted in NON-sorted order so the test can
    assert the route sorts by `order` rather than by insert sequence.
    """
    trip = Trip(
        user_id=user_id,
        destination="Goa",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        budget_total=Decimal("40000.00"),
        currency="INR",
        group_size=2,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    for day_num in (1, 2):
        day = Day(
            trip_id=trip.id,
            day_number=day_num,
            date=date(2026, 7, day_num),
            summary=f"Day {day_num} summary",
        )
        db.add(day)
        db.flush()

        # Insert blocks with order 3, 1, 2 — route must sort.
        for block_order in (3, 1, 2):
            block = Block(
                day_id=day.id,
                order=block_order,
                type="venue",
                venue_name=f"Day{day_num} Venue{block_order}",
                duration_minutes=60,
                est_cost=Decimal("500.00"),
                currency="INR",
                locked=False,
            )
            db.add(block)
            db.flush()
            db.add(
                Source(
                    block_id=block.id,
                    url=f"https://example.com/d{day_num}-b{block_order}",
                    source_type="blog",
                )
            )

    db.commit()
    db.refresh(trip)
    return trip


def test_full_returns_401_without_token(client: TestClient) -> None:
    resp = client.get(f"/trips/{uuid.uuid4()}/full")
    assert resp.status_code == 401


def test_full_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    resp = client.get(f"/trips/{uuid.uuid4()}/full")
    assert resp.status_code == 404


def test_full_returns_200_with_empty_days_when_never_planned(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Trip row exists but no days were ever persisted — partial-failure
    path from 3.2 or a brand-new trip whose plan hasn't started.
    """
    client, user = authed_client
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
    )
    db_session.add(trip)
    db_session.commit()
    db_session.refresh(trip)

    resp = client.get(f"/trips/{trip.id}/full")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(trip.id)
    assert body["destination"] == "Goa"
    # Top-level trip fields preserved from TripRead.
    assert body["user_id"] == str(user.id)
    assert body["status"] == "draft"
    # Empty days array — the load-bearing signal for "nothing to render yet."
    assert body["days"] == []


def test_full_returns_full_hierarchy_sorted(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """End-to-end shape check: trip → days[] → blocks[] (sorted by order) →
    sources[] (nested under each block).
    """
    client, user = authed_client
    trip = _make_full_trip(db_session, user.id)

    resp = client.get(f"/trips/{trip.id}/full")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Top-level trip envelope.
    assert body["id"] == str(trip.id)
    assert body["destination"] == "Goa"
    assert body["budget_total"] == "40000.00"

    # Days are sorted by day_number ascending.
    days = body["days"]
    assert len(days) == 2
    assert [d["day_number"] for d in days] == [1, 2]
    assert days[0]["summary"] == "Day 1 summary"

    # Blocks within each day are sorted by `order`, NOT by insert sequence.
    for day in days:
        blocks = day["blocks"]
        assert len(blocks) == 3
        assert [b["order"] for b in blocks] == [1, 2, 3], (
            "blocks must be sorted by `order`; insert sequence was 3,1,2"
        )

    # Sources nested under blocks (one per block in this fixture).
    first_block = days[0]["blocks"][0]
    assert len(first_block["sources"]) == 1
    src = first_block["sources"][0]
    assert src["url"].startswith("https://example.com/")
    assert src["source_type"] == "blog"
