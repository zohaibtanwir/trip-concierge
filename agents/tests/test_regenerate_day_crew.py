"""Day-scoped regenerate crew — config and output parsing.

Slice 3.3 commit 4. Mocked-LLM only.

Key differences from refine_crew (Process.hierarchical, 4 agents):
1. Process.sequential — narrow scope, no manager needed.
2. Three agents only (Researcher, Local Expert, Logistics) — Budget Auditor
   skipped per design call: single-day regen rarely shifts trip-level cost
   materially, audit overhead not worth the LLM tokens.
3. Output is a single Day Pydantic, not AuditedPlan. Worker splices the
   day's locked blocks back in afterward (commit 4 design Q3 = option (a)).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from crewai import Process

import trip_agents.crew as crew_mod
from trip_agents.schemas import Block, Day


def _day_result() -> MagicMock:
    """Stand-in CrewOutput whose .pydantic carries a Day with the regenerated
    blocks (for the unlocked positions; worker splices locked ones back in)."""
    day = Day(
        day_number=2,
        date="2026-07-16",
        summary="Beach + food day",
        blocks=[
            Block(order=1, type="venue", venue_name="New venue 1", duration_minutes=60),
            Block(order=3, type="meal", venue_name="New meal 3", duration_minutes=90),
        ],
    )
    result = MagicMock()
    result.pydantic = day
    return result


def _trip_context() -> dict[str, Any]:
    return {"destination": "Goa, India", "currency": "INR", "budget_total": 40000.0}


def _target_day() -> dict[str, Any]:
    return {"day_number": 2, "date": "2026-07-16", "summary": "Beach + food day"}


def test_regenerate_day_uses_sequential_process() -> None:
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _day_result()
        return instance

    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.regenerate_day(
            trip_context=_trip_context(),
            target_day=_target_day(),
            locked_blocks=[],
            unlocked_positions=[1, 3],
            hint="more food",
        )

    assert captured["process"] == Process.sequential, (
        f"regenerate_day() must use Process.sequential, got {captured.get('process')!r}"
    )


def test_regenerate_day_excludes_budget_auditor() -> None:
    """Three agents only — Auditor skipped for single-day regen. The agent
    list shouldn't change between minor refactors without explicit intent.
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _day_result()
        return instance

    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.regenerate_day(
            trip_context=_trip_context(),
            target_day=_target_day(),
            locked_blocks=[],
            unlocked_positions=[1, 3],
        )

    agents = captured.get("agents", [])
    assert len(agents) == 3, f"expected 3 agents (no Auditor), got {len(agents)}"
    roles = [getattr(a, "role", "").lower() for a in agents]
    assert not any("auditor" in r for r in roles), (
        f"Budget Auditor must not be in the regenerate_day crew; got roles={roles}"
    )


def test_regenerate_day_returns_day_dict() -> None:
    """Output parsing: returns a Day.model_dump() dict with blocks for the
    unlocked positions. Worker splices locked blocks back in.
    """
    with patch.object(crew_mod, "Crew") as mock_crew_cls:
        mock_crew_cls.return_value.kickoff.return_value = _day_result()
        out = crew_mod.regenerate_day(
            trip_context=_trip_context(),
            target_day=_target_day(),
            locked_blocks=[],
            unlocked_positions=[1, 3],
        )

    assert isinstance(out, dict)
    assert out["day_number"] == 2
    assert len(out["blocks"]) == 2
    assert {b["order"] for b in out["blocks"]} == {1, 3}
