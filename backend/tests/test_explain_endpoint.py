"""GET /trips/{trip_id}/explain/{block_id} — pure-read explain route.

Slice 3.4b commit 3. The route reads Block + Sources + the latest
JobRun.agent_summary excerpt for the block. No outbound calls, no
LLM, no writes.

Load-bearing contract per slice-opening Q3:

**Gap-surfacing**: when JobRun.agent_summary lacks a rationale for
this block (the qek-bug state), the response body has
`rationale: null` — NOT empty string, NOT a placeholder message.
The MCP tool (commit 4) branches on `is None` to render the
gap-text formatter. Backend reports the data state honestly;
presentation lives in the formatter.

**user_source_matches**: list of `{user_source_id, url}` pairs
where the Block's Source URLs overlap with any UserSource URL on
the trip. Empty list when no overlap. The formatter renders the
provenance line ("This came from your Reddit thread") only when
non-empty.

Five cases:
1. Happy path with rationale → 200 + rationale (str) + sources.
2. Gap path, no JobRun → 200 + rationale=None.
3. Gap path, JobRun exists but agent_summary lacks this block →
   200 + rationale=None.
4. user_source_matches populated when URL overlap exists.
5. 404 trip / 404 block / 401 — three sub-cases.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User
from app.models.user_source import UserSource


def _make_trip_with_block_and_source(
    db: Session,
    user: User,
    *,
    block_source_url: str = "https://reddit.com/r/IndiaTravel/abc",
) -> tuple[Trip, Block, Source]:
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

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
    db.refresh(block)

    source = Source(
        block_id=block.id,
        url=block_source_url,
        source_type="reddit",
        excerpt="Locals say Anjuna is the best for sunsets",
        confidence_score=Decimal("0.85"),
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    return trip, block, source


def _attach_job_run(
    db: Session,
    trip_id: uuid.UUID,
    *,
    agent_summary: list[dict[str, Any]] | None = None,
) -> JobRun:
    jr = JobRun(
        job_id=f"jr-{uuid.uuid4().hex[:8]}",
        trip_id=trip_id,
        kind="plan",
        status="succeeded",
        agent_summary=agent_summary or [],
    )
    db.add(jr)
    db.commit()
    db.refresh(jr)
    return jr


async def test_explain_happy_path_returns_rationale_sources_and_block_meta(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Rationale recorded for this block via JobRun.agent_summary —
    body surfaces the rationale string, sources array, and the block
    metadata.
    """
    client, user = authed_client
    trip, block, _ = _make_trip_with_block_and_source(db_session, user)
    _attach_job_run(
        db_session,
        trip.id,
        agent_summary=[
            {
                "block_id": str(block.id),
                "venue_name": "Anjuna Beach",
                "rationale": (
                    "Goa's most iconic sunset beach — beats Calangute for the "
                    "laid-back vibe the user asked for."
                ),
            }
        ],
    )

    resp = client.get(f"/trips/{trip.id}/explain/{block.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["block_id"] == str(block.id)
    assert body["venue_name"] == "Anjuna Beach"
    assert body["block_type"] == "venue"
    assert isinstance(body["rationale"], str)
    assert "Goa's most iconic" in body["rationale"]

    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"].startswith("https://reddit.com")
    assert body["sources"][0]["confidence_score"] == 0.85

    assert body["user_source_matches"] == []


async def test_explain_returns_rationale_null_when_no_job_run_exists(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Gap path A — no JobRun row at all (e.g., trip planned via direct
    persistence, or qek bug ate everything). rationale field MUST be
    null (JSON null), not empty string, not placeholder text.
    """
    client, user = authed_client
    trip, block, _ = _make_trip_with_block_and_source(db_session, user)
    # No _attach_job_run call.

    resp = client.get(f"/trips/{trip.id}/explain/{block.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["rationale"] is None, (
        "gap path must surface rationale=null, not placeholder text. "
        "Placeholder rendering is the MCP formatter's job."
    )
    # Sources still rendered.
    assert len(body["sources"]) == 1


async def test_explain_returns_rationale_null_when_agent_summary_lacks_this_block(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Gap path B — JobRun exists; agent_summary has entries for OTHER
    blocks but not this one. Distinct from gap A; both hit the same
    backend contract (rationale: null).
    """
    client, user = authed_client
    trip, block, _ = _make_trip_with_block_and_source(db_session, user)
    # agent_summary mentions a different block_id.
    _attach_job_run(
        db_session,
        trip.id,
        agent_summary=[
            {
                "block_id": str(uuid.uuid4()),  # different block
                "venue_name": "Some Other Venue",
                "rationale": "rationale for the other block",
            }
        ],
    )

    resp = client.get(f"/trips/{trip.id}/explain/{block.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rationale"] is None


async def test_explain_surfaces_user_source_matches_when_url_overlaps(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """A UserSource on this trip carries the same URL as the Block's
    Source — surface the overlap with user_source_id + url. The
    formatter renders "this came from your Reddit thread" when
    user_source_matches is non-empty.
    """
    client, user = authed_client
    shared_url = "https://reddit.com/r/IndiaTravel/anjuna"
    trip, block, _ = _make_trip_with_block_and_source(db_session, user, block_source_url=shared_url)

    user_source = UserSource(
        trip_id=trip.id,
        url=shared_url,
        raw_text="Anjuna is the best",
        content_type="url_fetched/html",
    )
    db_session.add(user_source)
    db_session.commit()
    db_session.refresh(user_source)

    resp = client.get(f"/trips/{trip.id}/explain/{block.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["user_source_matches"]) == 1
    match = body["user_source_matches"][0]
    assert match["url"] == shared_url
    assert match["user_source_id"] == str(user_source.id)


def test_explain_returns_401_without_token(client: TestClient) -> None:
    """Auth gate — separated from the 404 tests to avoid the
    authed_client fixture mutating the shared TestClient's headers.
    Slice 3.4a precedent.
    """
    resp = client.get(f"/trips/{uuid.uuid4()}/explain/{uuid.uuid4()}")
    assert resp.status_code == 401


async def test_explain_returns_404_for_unknown_trip_or_block(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Two sub-cases:
    - 404 "trip not found" when trip_id is unknown.
    - 404 "block not found on this trip" when block_id isn't on this
      trip (route-layer defense against UUID hallucination).
    """
    client, user = authed_client

    r_no_trip = client.get(f"/trips/{uuid.uuid4()}/explain/{uuid.uuid4()}")
    assert r_no_trip.status_code == 404
    assert "trip" in r_no_trip.json()["detail"].lower()

    trip, _real_block, _ = _make_trip_with_block_and_source(db_session, user)
    r_no_block = client.get(f"/trips/{trip.id}/explain/{uuid.uuid4()}")
    assert r_no_block.status_code == 404
    assert "block" in r_no_block.json()["detail"].lower()
