"""Live test: full sequential crew (Researcher → Local Expert → Logistics).

Marked @pytest.mark.live so CI skips it. Run locally with:
    cd agents && uv run pytest -m live

Asserts shape, not content — LLM output is non-deterministic and any
content assertion would be flaky. Trace upload to Langfuse is verified
manually in the Langfuse UI.

After slice 2.2 the final task is Logistics, so the crew output is a
day-by-day itinerary keyed by `days`, each day with an ordered `blocks`
array.
"""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_full_crew_kickoff_produces_day_by_day_itinerary() -> None:
    from crew import run

    result = run(
        destination="Goa, India",
        start_date="2026-07-01",
        end_date="2026-07-03",
        budget_total=40000,
        currency="INR",
        vibe="chill, lots of food, no parties",
        group_size=2,
        pace="balanced",
    )

    assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
    days = result.get("days")
    assert isinstance(days, list) and len(days) >= 1, (
        f"expected non-empty `days` array; got {result!r}"
    )

    # Each day must have an ordered list of blocks. The blocks themselves
    # come from Logistics and should have at least a venue name. We're
    # lenient on field names because LLM phrasing varies.
    for day in days:
        assert isinstance(day, dict), f"day is not a dict: {day!r}"
        blocks = day.get("blocks")
        assert isinstance(blocks, list) and len(blocks) >= 1, f"day has no blocks: {day!r}"
        for block in blocks:
            assert isinstance(block, dict)
            name_keys = {"venue_name", "name", "title"}
            assert any(k in block for k in name_keys), (
                f"block missing a name field: keys={list(block)!r}"
            )
