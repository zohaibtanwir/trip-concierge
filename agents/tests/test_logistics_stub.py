"""Logistics Planner: canonical strings + sequential 3-agent crew composition."""

from __future__ import annotations

from crewai import Process

from trip_agents.crew import _build_crew
from trip_agents.local_expert import local_expert
from trip_agents.logistics import logistics_planner
from trip_agents.researcher import researcher


def test_logistics_matches_prompts_md() -> None:
    assert logistics_planner.role == "Logistics Planner"
    assert "day-by-day itinerary" in logistics_planner.goal
    assert "former tour operations manager" in logistics_planner.backstory
    assert logistics_planner.allow_delegation is True


def test_crew_now_has_three_agents_in_order() -> None:
    crew = _build_crew()
    assert crew.process == Process.sequential
    assert [a.role for a in crew.agents] == [
        researcher.role,
        local_expert.role,
        logistics_planner.role,
    ]
    assert len(crew.tasks) == 3
    # Planning must consume the expertise task as context.
    planning_task = crew.tasks[2]
    assert planning_task.context is not None
    assert crew.tasks[1] in planning_task.context, (
        "Planning task should have local_expertise_task as context — prompts.md §3.3"
    )
