"""Local Expert: canonical-string check + sequential crew composition.

The live-mode behavior (Local Expert narrows + adds why_this_not_that)
is covered in test_researcher_live.py — that's the only place it's
cheap to verify, because narrowing happens inside the LLM.
"""

from __future__ import annotations

from crewai import Process

from crew import _build_crew
from local_expert import local_expert
from researcher import researcher


def test_local_expert_matches_prompts_md() -> None:
    assert local_expert.role == "Local Expert"
    assert "Narrow the Researcher's candidates down to the best options" in local_expert.goal
    assert "lived in dozens of cities" in local_expert.backstory
    assert local_expert.allow_delegation is True


def test_crew_is_sequential_with_both_agents() -> None:
    crew = _build_crew()
    assert crew.process == Process.sequential
    assert [a.role for a in crew.agents] == [researcher.role, local_expert.role]
    assert len(crew.tasks) == 2
    # Local Expert's task must consume the Researcher's output via context.
    expertise_task = crew.tasks[1]
    assert expertise_task.context is not None
    assert crew.tasks[0] in expertise_task.context, (
        "Local Expert task should have research_task as context — see prompts.md §3.2"
    )
