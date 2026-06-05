"""Slice 225 — pin the max_tokens override on the constructed LLM.

CrewAI 1.14.5's Anthropic provider hardcodes max_tokens=4096 as default
(crewai/llms/providers/anthropic/completion.py:159). Under our crew's
legacy tool_use path (Sonnet 4.6 isn't in NATIVE_STRUCTURED_OUTPUT_MODELS
in that CrewAI version), 4096 is right at the cliff edge for the TripPlan
schema — producing intermittent `input_value={}` ValidationError failures.

2/2 success at max_tokens=16000 vs ~33% baseline success at 4096 (per
the slice 225 diagnosis arc) confirmed the fix. This test pins the
override so a future llm.py edit can't silently drop it.
"""

from __future__ import annotations

from unittest.mock import patch

from trip_agents.llm import build_llm


def test_build_llm_sets_max_tokens_to_16000() -> None:
    """The LLM constructed via build_llm() must declare max_tokens=16000.

    Pinning the slice 225 fix. If a future contributor drops the
    max_tokens kwarg from llm.py's LLM(...) construction, this test
    fails loudly rather than letting the bug-blocking-all-happy-path-
    trips return silently under the next intermittent run.
    """
    # build_llm() short-circuits to None without ANTHROPIC_API_KEY.
    # Patch settings so we exercise the construction path under test.
    with patch("trip_agents.llm.settings") as mock_settings:
        mock_settings.anthropic_api_key = "test-key-not-real"
        mock_settings.anthropic_model = "claude-sonnet-4-6"
        # Skip Langfuse init — it tries to read its own settings.
        with patch("trip_agents.llm.get_langfuse", return_value=None):
            llm = build_llm()

    assert llm is not None, "build_llm() must return an LLM when api_key is set"
    assert llm.max_tokens == 16000, (
        f"slice 225: expected max_tokens=16000, got {llm.max_tokens!r}. "
        "The CrewAI Anthropic provider's 4096 default is right at the "
        "cliff edge for TripPlan under the legacy tool_use path — see "
        "crewai/llms/providers/anthropic/completion.py:159 + the "
        "NATIVE_STRUCTURED_OUTPUT_MODELS allow-list excluding Sonnet 4.6."
    )
