"""Live test: real Anthropic + Tavily call via CrewAI kickoff.

Marked @pytest.mark.live so CI skips it. Run locally with:
    cd agents && uv run pytest -m live

Asserts shape, not content — LLM output is non-deterministic and any
content assertion would be flaky. Trace upload to Langfuse is verified
manually in the Langfuse UI.
"""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_researcher_kickoff_returns_candidates() -> None:
    from crew import run

    result = run(
        destination="Goa, India",
        budget_total=40000,
        currency="INR",
        vibe="chill, lots of food, no parties",
        group_size=2,
    )

    assert isinstance(result, list), f"expected list, got {type(result).__name__}"
    # Local Expert narrows; >=1 is the lower bound. Researcher proposes 3-5
    # per category (3 categories), Local Expert keeps a subset.
    assert len(result) >= 1, f"expected at least 1 candidate, got {len(result)}"

    for item in result:
        assert isinstance(item, dict)
        assert isinstance(item.get("name"), str) and item["name"], (
            f"missing or empty name: {item!r}"
        )
        urls = item.get("source_urls") or item.get("source_url")
        if isinstance(urls, str):
            urls = [urls]
        assert isinstance(urls, list) and len(urls) >= 1, (
            f"every candidate must include at least one source URL: {item!r}"
        )

    # Local Expert's contract (prompts.md §1.2 + §3.2): every chosen item
    # must carry a why_this_not_that rationale. Use a tolerant accessor —
    # the LLM sometimes uses snake_case, sometimes spaces or camelCase.
    def _has_why(item: dict[str, object]) -> bool:
        keys = {k.lower().replace(" ", "_").replace("-", "_") for k in item}
        return "why_this_not_that" in keys or "whythisnotthat" in keys

    assert any(_has_why(item) for item in result), (
        "no candidate has a why_this_not_that field; Local Expert may not have run. "
        f"sample item keys: {list(result[0].keys())}"
    )
