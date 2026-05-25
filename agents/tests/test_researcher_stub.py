"""Stubbed Researcher: structure check on crew.run() output.

The agent does not call an LLM in this slice — crew.run() returns
fixture data. Slice 1.4 swaps the fixture return for a real
crew.kickoff() against Anthropic.
"""

from __future__ import annotations

from crew import run
from researcher import researcher


def test_crew_run_returns_three_candidates() -> None:
    result = run(destination="Goa")
    assert isinstance(result, list)
    assert len(result) == 3


def test_each_candidate_has_required_fields() -> None:
    result = run(destination="Goa")
    for item in result:
        assert isinstance(item.get("name"), str) and item["name"]
        assert isinstance(item.get("rationale"), str) and item["rationale"]
        urls = item.get("source_urls")
        assert isinstance(urls, list) and len(urls) >= 1, (
            "every candidate must include at least one source URL per prompts.md §1.1"
        )


def test_researcher_agent_matches_prompts_md() -> None:
    """role/goal/backstory must be the verbatim canonical strings."""
    assert researcher.role == "Travel Researcher"
    assert "Find 3-5 destination candidates" in researcher.goal
    assert "meticulous travel researcher with 15 years" in researcher.backstory
    assert researcher.allow_delegation is True
