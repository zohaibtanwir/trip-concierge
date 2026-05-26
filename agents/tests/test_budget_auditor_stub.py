"""Budget Auditor: canonical strings + composition invariants."""

from __future__ import annotations

from budget_auditor import budget_auditor
from crew import _build_crew


def test_budget_auditor_matches_prompts_md() -> None:
    assert budget_auditor.role == "Budget Auditor"
    assert "apply surgical revisions directly" in budget_auditor.goal
    assert "adversarial reviewer" in budget_auditor.backstory
    # Surgeon mode, not referee. Enforced at the Agent level so the LLM
    # CANNOT delegate even if it wants to.
    assert budget_auditor.allow_delegation is False


def test_budget_auditor_NOT_in_main_crew() -> None:
    """The Auditor runs as a Python-orchestrated loop after the main crew,
    not as a sequential step inside it. If this test fails the audit
    retry loop has been turned back into an LLM-controlled flow.
    """
    crew = _build_crew()
    roles = [a.role for a in crew.agents]
    assert "Budget Auditor" not in roles, (
        f"Budget Auditor must be orchestrated outside the main crew; found in main crew: {roles}"
    )
    assert len(crew.agents) == 3, (
        "Main crew should be 3 agents (Researcher, Local Expert, Logistics); "
        f"got {len(crew.agents)}"
    )
