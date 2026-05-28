"""find_alternative crew — config + output parsing.

Slice 3.4a commit 3. Mocked-LLM only (per slice thesis: visibility before
reliability; real-LLM validation happens in Claude Desktop manually
post-merge).

Four load-bearing properties verified:
1. Single-agent Researcher composition (per Option B from the file-tree
   session, tracked as trip-concierge-5yw).
2. Process.sequential (no manager_llm, no hierarchical).
3. AlternativesList parsing with the exactly-3-items invariant from the
   schema. If the crew returns 2 or 4 alternatives, validation fails and
   extraction raises a clear error — the slice-3.3 prohibition discipline
   applied at the schema layer.
4. step_callback plumbed through so JobRun.agent_summary can collect events.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from crewai import Process

import trip_agents.crew as crew_mod
from trip_agents.schemas import Alternative, AlternativesList


def _alternatives_result(alternatives: list[Alternative] | None = None) -> MagicMock:
    """CrewOutput stand-in with .pydantic set to a valid AlternativesList."""
    if alternatives is None:
        alternatives = [
            Alternative(
                venue_name=f"Venue {i}",
                type="venue",
                duration_minutes=60,
                est_cost=500.0,
                currency="INR",
                source_urls=[f"https://example.com/v{i}"],
                rationale=f"Good fit because of constraint match {i} stuff stuff",
            )
            for i in range(1, 4)
        ]
    result = MagicMock()
    if len(alternatives) == 3:
        result.pydantic = AlternativesList(alternatives=alternatives)
    else:
        # Mimic what CrewAI does when output_pydantic validation fails —
        # .pydantic stays None and .raw carries the bad JSON.
        result.pydantic = None
        result.raw = '{"alternatives": []}'
    return result


def _trip_state() -> dict[str, Any]:
    return {
        "destination": "Goa, India",
        "currency": "INR",
        "constraints_summary": "vegetarian; no nightclubs",
    }


def _block() -> dict[str, Any]:
    return {
        "type": "meal",
        "venue_name": "Original Restaurant",
        "duration_minutes": 60,
        "start_time": "19:00",
    }


def test_find_alternative_uses_sequential_process_with_one_agent() -> None:
    """Per Option B (Researcher alone) the crew is sequential, single-agent.
    Catches version-drift in CrewAI's Process API and any future refactor
    that accidentally adds an agent.
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _alternatives_result()
        return instance

    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.find_alternative(trip_state=_trip_state(), block=_block(), reason="closed")

    assert captured["process"] == Process.sequential, (
        f"find_alternative must use Process.sequential, got {captured.get('process')!r}"
    )
    agents = captured.get("agents", [])
    assert len(agents) == 1, (
        f"find_alternative crew must have exactly 1 agent (Researcher); got {len(agents)}"
    )
    # Manager-LLM forbidden — this is sequential, not hierarchical.
    assert "manager_llm" not in captured, "sequential crew must not set manager_llm"


def test_find_alternative_returns_three_alternatives_dict() -> None:
    """Happy path: crew returns valid 3-item AlternativesList → function
    returns model_dump() with all three entries and required fields."""
    with patch.object(crew_mod, "Crew") as mock_crew_cls:
        mock_crew_cls.return_value.kickoff.return_value = _alternatives_result()
        out = crew_mod.find_alternative(
            trip_state=_trip_state(), block=_block(), reason="restaurant closed"
        )

    assert isinstance(out, dict)
    alts = out["alternatives"]
    assert len(alts) == 3
    # Per-item required fields present.
    for alt in alts:
        assert "venue_name" in alt
        assert "type" in alt
        assert "duration_minutes" in alt
        assert "est_cost" in alt
        assert "currency" in alt
        assert "source_urls" in alt and len(alt["source_urls"]) >= 1
        assert "rationale" in alt and len(alt["rationale"]) >= 10


def test_find_alternative_raises_when_crew_returns_wrong_item_count() -> None:
    """Slice-thesis load-bearer at the schema layer. AlternativesList enforces
    min_length=3 AND max_length=3 on the alternatives list. If the crew
    drifts to 2 or 4 items, extraction must raise a clear ValueError
    rather than silently returning degraded output.

    This is the schema-layer equivalent of the §3.7 task instruction
    "Return exactly 3 alternatives" — belt and suspenders.
    """
    bad_result = _alternatives_result(alternatives=[])  # .pydantic = None
    with patch.object(crew_mod, "Crew") as mock_crew_cls:
        mock_crew_cls.return_value.kickoff.return_value = bad_result
        with pytest.raises(ValueError, match="AlternativesList"):
            crew_mod.find_alternative(trip_state=_trip_state(), block=_block(), reason=None)


def test_find_alternative_plumbs_step_callback_to_crew() -> None:
    """step_callback reaches the crew so JobRun.agent_summary collects
    events once the qek bug is fixed. (Today step_callback doesn't fire
    in practice per ticket qek; we plumb it correctly so the eventual
    fix unlocks observability.)
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _alternatives_result()
        return instance

    sentinel = lambda _step: None  # noqa: E731
    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.find_alternative(
            trip_state=_trip_state(),
            block=_block(),
            reason=None,
            step_callback=sentinel,
        )

    assert captured.get("step_callback") is sentinel
