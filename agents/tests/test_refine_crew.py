"""Hierarchical refine crew — config and output parsing.

Slice 3.3 commit 4. Mocked-LLM only (per slice thesis: visibility before
reliability; real-LLM validation happens in Claude Desktop manually after
commit 5).

Three load-bearing properties verified here:
1. The crew is constructed with Process.hierarchical AND a manager_llm
   (CrewAI requires manager_llm or manager_agent for hierarchical mode).
2. All four agents are passed to the crew (Researcher, Local Expert,
   Logistics, Budget Auditor).
3. The result is parsed into an AuditedPlan dict — same shape as plan_trip's
   output so persist_audited_plan can consume it unchanged (option (a) for
   Q1 from the commit 4 design proposal).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from crewai import Process

import trip_agents.crew as crew_mod
from trip_agents.schemas import AuditedPlan, Block, Day


def _audited_result() -> MagicMock:
    """Stand-in for CrewAI's CrewOutput object. Sets .pydantic to a real
    AuditedPlan so _extract_audited_plan can pull it cleanly.
    """
    audited = AuditedPlan(
        approved=True,
        days=[
            Day(
                day_number=1,
                blocks=[
                    Block(order=1, type="venue", venue_name="V1", duration_minutes=60),
                ],
            ),
        ],
        per_day_costs=[1000.0],
        total_cost=1000.0,
        currency="USD",
        constraints_violated=[],
        explanation="",
        revision_log=["Pass 1: nothing to revise"],
    )
    result = MagicMock()
    result.pydantic = audited
    return result


def _trip_state() -> dict[str, Any]:
    return {
        "destination": "Goa, India",
        "budget_total": 40000.0,
        "currency": "INR",
        "group_size": 1,
        "pace": "balanced",
        "days": [
            {
                "day_number": 1,
                "date": "2026-07-15",
                "summary": "Beach day",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Anjuna Beach",
                        "duration_minutes": 120,
                        "locked": False,
                    },
                ],
            },
        ],
    }


def test_refine_uses_hierarchical_process_with_manager_llm() -> None:
    """The load-bearing CrewAI config: Process.hierarchical + manager_llm.

    CrewAI raises at runtime if hierarchical is selected without a manager
    (manager_llm or manager_agent). This test catches version-drift in the
    manager_llm parameter name — if CrewAI ever renames it (or makes it
    required differently), this fails loudly instead of producing empty
    crew output silently.
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _audited_result()
        return instance

    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.refine(trip_state=_trip_state(), refinement_description="make Day 1 chiller")

    assert captured["process"] == Process.hierarchical, (
        f"refine() must use Process.hierarchical, got {captured.get('process')!r}"
    )
    assert "manager_llm" in captured, (
        "refine() must pass manager_llm — CrewAI requires it for hierarchical mode. "
        "If CrewAI renamed this parameter in a version bump, surface it here."
    )


def test_refine_passes_all_four_agents() -> None:
    """All four agents reach the hierarchical crew so the manager can route
    among them. Budget Auditor included — per prompts.md §2 and the design
    call to have audit done inside the hierarchical crew (option (a) for Q1).
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _audited_result()
        return instance

    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.refine(trip_state=_trip_state(), refinement_description="anything")

    agent_roles = [getattr(a, "role", str(a)) for a in captured.get("agents", [])]
    assert len(agent_roles) == 4, f"expected 4 agents in hierarchical crew, got {agent_roles}"


def test_refine_returns_audited_plan_dict() -> None:
    """Output parsing: refine() returns AuditedPlan.model_dump(). Same shape
    as plan_trip's output → persist_audited_plan consumes it unchanged.
    """
    with patch.object(crew_mod, "Crew") as mock_crew_cls:
        mock_crew_cls.return_value.kickoff.return_value = _audited_result()
        out = crew_mod.refine(trip_state=_trip_state(), refinement_description="make it chill")

    assert isinstance(out, dict)
    assert out["approved"] is True
    assert isinstance(out["days"], list) and len(out["days"]) == 1
    assert "revision_log" in out


def test_refine_plumbs_step_callback_to_crew() -> None:
    """The worker's step_callback must reach the hierarchical crew so the
    JobRun.agent_summary column collects per-agent events (when step_callback
    bug `qek` is eventually fixed — for now it doesn't fire, but the plumbing
    must be correct so the eventual fix unlocks observability).
    """
    captured: dict[str, Any] = {}

    def fake_crew_init(*_args: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        instance = MagicMock()
        instance.kickoff.return_value = _audited_result()
        return instance

    sentinel = lambda _step: None  # noqa: E731
    with patch.object(crew_mod, "Crew", side_effect=fake_crew_init):
        crew_mod.refine(
            trip_state=_trip_state(),
            refinement_description="anything",
            step_callback=sentinel,
        )

    assert captured.get("step_callback") is sentinel
