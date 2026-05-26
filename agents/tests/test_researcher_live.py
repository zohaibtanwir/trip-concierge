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
    assert len(result) >= 3, f"expected at least 3 candidates, got {len(result)}"

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
