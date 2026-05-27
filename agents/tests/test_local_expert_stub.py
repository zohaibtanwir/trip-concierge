"""Local Expert: canonical-string check + sequential crew composition.

The live-mode behavior (Local Expert narrows + adds why_this_not_that)
is covered in test_researcher_live.py — that's the only place it's
cheap to verify, because narrowing happens inside the LLM.
"""

from __future__ import annotations

from crewai import Process

from trip_agents.crew import _build_crew
from trip_agents.local_expert import local_expert
from trip_agents.researcher import researcher


def test_local_expert_matches_prompts_md() -> None:
    assert local_expert.role == "Local Expert"
    assert "Narrow the Researcher's candidates down to the best options" in local_expert.goal
    assert "lived in dozens of cities" in local_expert.backstory
    assert local_expert.allow_delegation is True


def test_local_expert_task_consumes_research_via_context() -> None:
    """Per prompts.md §3.2: Local Expert never invents — it narrows what
    Researcher surfaced. Sequential crew composition (count of agents)
    can grow in later slices; the wiring rule here is the invariant.
    """
    crew = _build_crew()
    assert crew.process == Process.sequential
    roles = [a.role for a in crew.agents]
    assert researcher.role in roles
    assert local_expert.role in roles
    expertise_idx = next(i for i, t in enumerate(crew.tasks) if t.agent == local_expert)
    research_idx = next(i for i, t in enumerate(crew.tasks) if t.agent == researcher)
    assert research_idx < expertise_idx, "Local Expert must run AFTER Researcher"
    expertise_task = crew.tasks[expertise_idx]
    assert expertise_task.context is not None
    assert crew.tasks[research_idx] in expertise_task.context
