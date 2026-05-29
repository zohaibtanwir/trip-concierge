"""trip_export — JSON + Markdown rendering helpers.

Slice 3.5 commit 1. The service takes a TripFullRead Pydantic
schema (the same one GET /trips/{id}/full returns) and emits a
string the route layer ships to the client.

Stdlib only — no new deps, no Decimal/date handling weirdness
because Pydantic's model_dump(mode="json") normalizes both.

Six load-bearing cases pin:
1. render_json roundtrips through json.loads (structural assertion
   surface).
2. render_markdown contains destination + day headers + venue names
   (happy path).
3. Empty days → graceful "no days planned" line (don't crash on a
   trip persisted before the crew finished).
4. Empty blocks for a day → graceful "no blocks yet for this day"
   line (gap-surfacing discipline, matches slice-3.3
   format_trip_succeeded behavior).
5. Optional fields (start_time=None, date=None, est_cost=None,
   confidence_score=None) → don't appear as literal "None" strings.
6. constraints + pace + currency surface in JSON but NOT in
   Markdown (markdown is human-pasteable; constraints structure
   isn't useful in a text app — load-bearing format-design choice).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.schemas.day import BlockRead, DayRead, SourceRead
from app.schemas.trip import TripFullRead
from app.services.trip_export import render_json, render_markdown


def _make_trip(
    *,
    days: list[DayRead] | None = None,
    constraints: dict | None = None,
) -> TripFullRead:
    """Construct a TripFullRead fixture. Optional days override; default
    is one Day with one Block with one Source.
    """
    if days is None:
        days = [
            DayRead(
                id=uuid.uuid4(),
                day_number=1,
                date=date(2026, 7, 15),
                summary="Beach day at Anjuna",
                blocks=[
                    BlockRead(
                        id=uuid.uuid4(),
                        order=1,
                        type="venue",
                        venue_name="Anjuna Beach",
                        lat=Decimal("15.5722"),
                        lng=Decimal("73.7400"),
                        start_time="09:00",
                        duration_minutes=120,
                        est_cost=Decimal("0.00"),
                        currency="INR",
                        locked=False,
                        notes="",
                        sources=[
                            SourceRead(
                                id=uuid.uuid4(),
                                url="https://reddit.com/r/IndiaTravel/anjuna",
                                source_type="reddit",
                                excerpt="Locals say Anjuna is best for sunsets",
                                confidence_score=Decimal("0.85"),
                            )
                        ],
                    )
                ],
            )
        ]
    return TripFullRead(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status="succeeded",
        destination="Goa, India",
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 17),
        group_size=2,
        budget_total=Decimal("40000"),
        currency="INR",
        constraints=constraints if constraints is not None else {"rules": []},
        pace="balanced",
        created_at=datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC),
        days=days,
    )


def test_render_json_roundtrips_through_json_loads() -> None:
    """The structural assertion surface — if a future refactor produces
    non-JSON output, json.loads fails loudly. Asserts on shape AFTER
    parsing rather than on the raw string so whitespace/indent choices
    don't break tests.
    """
    trip = _make_trip()
    output = render_json(trip)

    parsed = json.loads(output)
    assert parsed["destination"] == "Goa, India"
    assert parsed["currency"] == "INR"
    assert len(parsed["days"]) == 1
    assert parsed["days"][0]["blocks"][0]["venue_name"] == "Anjuna Beach"
    assert parsed["days"][0]["blocks"][0]["sources"][0]["url"].startswith("https://reddit.com")


def test_render_markdown_contains_destination_and_day_headers() -> None:
    """Happy path. The output is human-pasteable and contains the
    venue + day structure the user expects to see in Notion / Apple
    Notes / WhatsApp.
    """
    trip = _make_trip()
    output = render_markdown(trip)

    # Destination shows in a heading.
    assert "Goa, India" in output
    # Day-level structure.
    assert "Day 1" in output
    # The block-level venue surfaces.
    assert "Anjuna Beach" in output
    # The start_time and duration land somewhere readable.
    assert "09:00" in output
    assert "120" in output
    # The source URL is included so the user retains the citation.
    assert "https://reddit.com/r/IndiaTravel/anjuna" in output


def test_render_markdown_gracefully_handles_trip_with_no_days() -> None:
    """A trip persisted before the crew finished (or qek-bug truncated
    output) may have zero days. The export shouldn't crash; it should
    say so plainly — slice-3.3 honest-broken discipline.
    """
    trip = _make_trip(days=[])
    output = render_markdown(trip)

    assert "Goa, India" in output
    # Some phrasing names the gap honestly.
    lower = output.lower()
    assert "no days" in lower or "not yet planned" in lower or "no itinerary" in lower


def test_render_markdown_gracefully_handles_day_with_no_blocks() -> None:
    """A Day with empty blocks list should surface as "no blocks yet"
    or similar — not silently omit the day or crash.
    """
    empty_day = DayRead(
        id=uuid.uuid4(),
        day_number=2,
        date=date(2026, 7, 16),
        summary="Beach day (TBD)",
        blocks=[],
    )
    trip = _make_trip(days=[empty_day])
    output = render_markdown(trip)

    assert "Day 2" in output
    lower = output.lower()
    assert "no blocks" in lower or "no plans" in lower or "tbd" in lower


def test_render_markdown_omits_literal_none_strings_for_optional_fields() -> None:
    """Optional fields (start_time, date, est_cost, confidence_score)
    are None for many real trips. The renderer must NOT emit literal
    "None" strings — those leak Python internals into user-facing text.
    """
    minimal_day = DayRead(
        id=uuid.uuid4(),
        day_number=1,
        date=None,
        summary="",
        blocks=[
            BlockRead(
                id=uuid.uuid4(),
                order=1,
                type="venue",
                venue_name="Some Venue",
                lat=None,
                lng=None,
                start_time=None,
                duration_minutes=60,
                est_cost=None,
                currency="INR",
                locked=False,
                notes="",
                sources=[
                    SourceRead(
                        id=uuid.uuid4(),
                        url="https://example.com",
                        source_type="other",
                        excerpt="",
                        confidence_score=None,
                    )
                ],
            )
        ],
    )
    trip = _make_trip(days=[minimal_day])
    output = render_markdown(trip)

    assert "None" not in output, "literal 'None' must not appear in user-facing markdown"
    assert "Some Venue" in output


def test_render_markdown_omits_constraints_while_json_includes_them() -> None:
    """Format-design choice: constraints structure is useful for
    programmatic re-import (JSON) but not for human pasting (Markdown).
    Pinning this so a future "let's add constraints to markdown" change
    is a deliberate decision, not an accidental copy-paste.
    """
    trip = _make_trip(
        constraints={
            "rules": [
                {"kind": "dietary", "value": "vegetarian"},
                {"kind": "no_go", "value": "nightclubs"},
            ]
        }
    )

    md = render_markdown(trip)
    parsed_json = json.loads(render_json(trip))

    # Markdown is for humans — constraints shouldn't appear.
    assert "vegetarian" not in md
    assert "nightclubs" not in md
    assert "kind" not in md.lower() or "dietary" not in md

    # JSON is for re-import — constraints MUST appear.
    assert parsed_json["constraints"]["rules"][0]["kind"] == "dietary"
    assert parsed_json["constraints"]["rules"][0]["value"] == "vegetarian"
    assert parsed_json["pace"] == "balanced"
    assert parsed_json["currency"] == "INR"
