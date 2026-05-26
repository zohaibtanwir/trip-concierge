"""Crew entrypoint.

`run()` calls the LLM via CrewAI's sequential process. `run_stub()`
keeps the fixture-load path from slice 1.3 so offline tests stay fast.

After slice 2.2 the crew composition is Researcher → Local Expert →
Logistics Planner. The final task is Logistics, so the crew output is
a day-by-day itinerary (not a flat candidates list). `run()` returns
that as a dict with a `days` array; `run_stub()` still returns the
slice-1.3 candidates fixture for the stub tests that pre-date the
shape change.

Slice 2.3 adds Budget Auditor; the output gains an audit-decision
layer on top of `days`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from crewai import Crew, Process
from langfuse import observe

from llm import get_langfuse
from local_expert import local_expert
from logistics import logistics_planner
from researcher import researcher
from tasks import make_local_expertise_task, make_planning_task, make_research_task

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
    "pace": "balanced",
}


def _build_crew() -> Crew:
    """Sequential crew: Researcher → Local Expert → Logistics Planner."""
    research = make_research_task()
    expertise = make_local_expertise_task(research)
    planning = make_planning_task(expertise)
    return Crew(
        agents=[researcher, local_expert, logistics_planner],
        tasks=[research, expertise, planning],
        process=Process.sequential,
        verbose=False,
    )


@observe(name="crew.run")
def run(destination: str, **overrides: Any) -> dict[str, Any]:
    """Live: kickoff the sequential crew. Returns the parsed Logistics output.

    Prefers CrewAI's Pydantic-validated output (`result.pydantic`) since the
    planning task is configured with `output_pydantic=TripPlan`. Falls back
    to JSON parsing of `str(result)` if Pydantic output is unavailable (e.g.
    LLM produced malformed JSON despite the schema constraint).
    """
    inputs: dict[str, Any] = {**DEFAULT_INPUTS, "destination": destination, **overrides}
    logger.info("crew.run.start", extra={"destination": destination})
    result = _build_crew().kickoff(inputs=inputs)

    raw = str(result)
    output: dict[str, Any] | None = None
    if hasattr(result, "pydantic") and result.pydantic is not None:
        output = result.pydantic.model_dump()
    else:
        parsed = _parse_json(raw)
        if isinstance(parsed, list):
            parsed = {"days": parsed}
        if isinstance(parsed, dict):
            output = parsed

    # Dump for offline debugging — JSON when we got a structured output,
    # raw text otherwise. Saves a re-run if anything down-stream breaks.
    debug_path = Path("/tmp") / "crew_last_output.json"
    with contextlib.suppress(OSError):
        debug_path.write_text(json.dumps(output, indent=2) if output else raw)

    if output is None:
        raise ValueError(
            f"could not extract days from LLM output (raw saved to {debug_path}): {raw[:300]!r}..."
        )

    logger.info("crew.run.success", extra={"days": len(output.get("days") or [])})
    client = get_langfuse()
    if client is not None:
        client.flush()
    return output


def run_stub(destination: str) -> list[dict[str, Any]]:
    """Offline: return the slice-1.3 candidates fixture. Used by stub tests."""
    _ = destination
    data: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    return data


def _parse_json(raw_output: str) -> Any:
    text = raw_output.strip()
    return _try_parse(text) or _try_fenced(text) or _try_balanced(text)


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
