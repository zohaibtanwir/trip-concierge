"""End-to-end live test: full 4-agent pipeline (Researcher → Local Expert →
Logistics → Budget Auditor) against real Anthropic + Tavily + Langfuse.

Marked @pytest.mark.live so CI skips it. Run locally with:
    cd agents && uv run pytest -m live

Asserts shape, not content — LLM output is non-deterministic. Trace upload
to Langfuse is verified manually in the UI.

After slice 2.3 the orchestrator returns an AuditedPlan dict — `days` from
Logistics (possibly revised by the Auditor), plus audit metadata
(`approved`, `revision_log`, `per_day_costs`, `total_cost`,
`constraints_violated`, `explanation`).
"""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_full_pipeline_returns_audited_itinerary() -> None:
    from trip_agents.crew import run

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

    # Days carried through from Logistics, possibly revised by Auditor.
    days = result.get("days")
    assert isinstance(days, list) and len(days) >= 1, (
        f"expected non-empty `days` array; got {result!r}"
    )
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

    # Auditor surface — these must all exist at the top level.
    assert isinstance(result.get("approved"), bool), (
        f"`approved` should be bool, got {type(result.get('approved')).__name__}"
    )
    assert isinstance(result.get("revision_log"), list), (
        f"`revision_log` should be list, got {type(result.get('revision_log')).__name__}"
    )
    assert isinstance(result.get("constraints_violated"), list)

    # Every revision_log entry the orchestrator emits is prefixed "Pass N: ".
    # An empty log is acceptable (pass 1 might have nothing to revise).
    for entry in result["revision_log"]:
        assert isinstance(entry, str)
        assert entry.startswith("Pass 1: ") or entry.startswith("Pass 2: "), (
            f"revision_log entry not prefixed by orchestrator: {entry!r}"
        )

    # If approved is False after the loop, an explanation should be present.
    if not result["approved"]:
        assert result.get("explanation"), (
            "approved=False outputs must include an explanation of the gap"
        )
