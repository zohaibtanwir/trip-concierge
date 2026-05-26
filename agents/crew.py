"""Crew entrypoint.

`run()` calls the LLM via CrewAI; `run_stub()` keeps the fixture-load
path from slice 1.3 so offline tests stay fast. Stub data also stays
useful as a fallback in dev when api keys aren't set.

In Phase 2 this expands to a four-agent sequential crew; for now it's
just the Researcher.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from crewai import Crew, Process
from langfuse import observe

from llm import get_langfuse
from local_expert import local_expert
from researcher import researcher
from tasks import make_local_expertise_task, make_research_task

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "researcher_output.json"

DEFAULT_INPUTS = {
    "start_date": "TBD",
    "end_date": "TBD",
    "group_size": 2,
    "budget_total": "unspecified",
    "currency": "USD",
    "vibe": "chill, well-researched",
    "constraints": "none specified",
    "user_sources": "none provided",
}


def _build_crew() -> Crew:
    """Sequential crew: Researcher finds candidates, Local Expert narrows them.

    Slice 2.1 added Local Expert. Slices 2.2/2.3 add Logistics + Budget Auditor.
    Local Expert receives the Researcher's output via task `context`, never
    invents new venues (prompts.md §1.2 behavior note).
    """
    research = make_research_task()
    expertise = make_local_expertise_task(research)
    return Crew(
        agents=[researcher, local_expert],
        tasks=[research, expertise],
        process=Process.sequential,
        verbose=False,
    )


def _extract_candidates(raw_output: str) -> list[dict[str, Any]]:
    """Parse the agent's text output into a flat candidate list.

    LLM output varies: sometimes a bare JSON object/array, sometimes a
    fenced ```json block, sometimes wrapped in prose. We try, in order:
    1. Whole text as JSON
    2. ```json (or ```) fenced block (closing fence optional)
    3. First balanced { ... } or [ ... ] substring

    The Researcher's expected_output is a JSON object with stays/activities/
    meals arrays — we flatten them into a list with a `category` tag.
    """
    text = raw_output.strip()
    parsed = _try_parse(text) or _try_fenced(text) or _try_balanced(text)
    if parsed is None:
        logger.error("crew.parse.failed", extra={"head": text[:500]})
        raise ValueError(f"could not extract JSON from LLM output: {text[:200]!r}...")

    if isinstance(parsed, list):
        return parsed

    flat: list[dict[str, Any]] = []
    for bucket in ("stays", "activities", "meals"):
        for item in parsed.get(bucket, []):
            flat.append({**item, "category": bucket})
    # Some prompts produce {"candidates": [...]} or similar — fall back to
    # the first list-valued field if our three buckets are empty.
    if not flat:
        for v in parsed.values():
            if isinstance(v, list) and v:
                return [x for x in v if isinstance(x, dict)]
    return flat


def _try_parse(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _try_fenced(text: str) -> Any | None:
    fenced = re.search(r"```(?:json)?\s*\n?(.+?)(?:```|\Z)", text, re.DOTALL)
    if not fenced:
        return None
    return _try_parse(fenced.group(1).strip())


def _try_balanced(text: str) -> Any | None:
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    parsed = _try_parse(text[start : i + 1])
                    if parsed is not None:
                        return parsed
    return None


@observe(name="researcher.run")
def run(destination: str, **overrides: Any) -> list[dict[str, Any]]:
    """Live: kickoff the CrewAI Researcher against Anthropic + Tavily.

    Wrapped in @observe so each call produces a Langfuse trace with the
    inputs, outputs, and duration. CrewAI's internal LLM calls live as
    spans under this top-level trace.
    """
    inputs: dict[str, Any] = {**DEFAULT_INPUTS, "destination": destination, **overrides}
    logger.info("crew.run.start", extra={"destination": destination})
    result = _build_crew().kickoff(inputs=inputs)
    raw = str(result)
    logger.info("crew.run.raw_head", extra={"head": raw[:500]})
    candidates = _extract_candidates(raw)
    logger.info("crew.run.success", extra={"count": len(candidates)})
    # Make sure the trace is flushed before we return (otherwise short-lived
    # processes might exit before the background uploader sends).
    client = get_langfuse()
    if client is not None:
        client.flush()
    return candidates


def run_stub(destination: str) -> list[dict[str, Any]]:
    """Offline: return the fixture from slice 1.3. Used by stub tests."""
    _ = destination
    data: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    return data
