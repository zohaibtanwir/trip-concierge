"""Crew entrypoint.

Pipeline as of slice 2.3:

    run(destination, ...) :=
        TripPlan = main_crew.kickoff()           # Researcher → Local Expert → Logistics
        AuditedPlan = run_audit(TripPlan, ...)   # Python loop, up to MAX_AUDIT_PASSES
        return AuditedPlan.model_dump()

The audit loop is Python, not LLM — each Auditor pass is its own
`Crew(agents=[budget_auditor], tasks=[make_audit_task()])` kickoff, with
the orchestrator deciding whether to run another pass. This:
  - Makes MAX_AUDIT_PASSES enforceable in code (model can't violate it)
  - Surfaces each pass as a separate Langfuse span
  - Produces a real revision_log we can inspect later for quality experiments

`run_stub()` keeps the slice-1.3 candidates fixture path for offline tests.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from crewai import Crew, Process
from langfuse import observe

from trip_agents.llm import get_langfuse
from trip_agents.local_expert import local_expert
from trip_agents.logistics import logistics_planner
from trip_agents.researcher import researcher
from trip_agents.schemas import AlternativesList, AuditedPlan, Day, TripPlan
from trip_agents.tasks import (
    make_audit_task,
    make_find_alternative_task,
    make_local_expertise_task,
    make_planning_task,
    make_refine_task,
    make_regenerate_day_task,
    make_research_task,
)

logger = logging.getLogger(__name__)

# Fixture lives at agents/tests/fixtures/, three levels up from this file
# (src/trip_agents/crew.py → agents/).
FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "researcher_output.json"
)

MAX_AUDIT_PASSES = 2

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
    "per_day_budget": "unspecified",
    "dietary": "none",
    "mobility": "none",
    "no_go_list": "none",
    "max_walking_km": "unspecified",
}


def _build_crew(step_callback: Callable[[Any], None] | None = None) -> Crew:
    """Sequential 3-agent crew: Researcher → Local Expert → Logistics Planner.

    Budget Auditor is NOT in this crew — it runs as a Python-orchestrated
    loop after this crew finishes. See run_audit().

    `step_callback` is plumbed through to CrewAI so the worker can collect
    per-agent step events for the JobRun.agent_summary column. None is fine
    when nothing's listening.
    """
    research = make_research_task()
    expertise = make_local_expertise_task(research)
    planning = make_planning_task(expertise)
    kwargs: dict[str, Any] = {
        "agents": [researcher, local_expert, logistics_planner],
        "tasks": [research, expertise, planning],
        "process": Process.sequential,
        "verbose": False,
    }
    if step_callback is not None:
        kwargs["step_callback"] = step_callback
    return Crew(**kwargs)


@observe(name="crew.run")
def run(
    destination: str,
    step_callback: Callable[[Any], None] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Live: main crew → audit loop. Returns the final AuditedPlan dict.

    `step_callback` is forwarded to the main crew and each audit pass so
    every agent step the worker observes lands in JobRun.agent_summary.
    """
    inputs: dict[str, Any] = {**DEFAULT_INPUTS, "destination": destination, **overrides}
    logger.info("crew.run.start", extra={"destination": destination})

    # 1. Main 3-agent crew produces a TripPlan.
    crew_result = _build_crew(step_callback=step_callback).kickoff(inputs=inputs)
    plan = _extract_trip_plan(crew_result)

    # 2. Audit loop owns retry policy.
    constraints = {
        "budget_total": inputs.get("budget_total"),
        "per_day_budget": inputs.get("per_day_budget"),
        "dietary": inputs.get("dietary"),
        "mobility": inputs.get("mobility"),
        "no_go_list": inputs.get("no_go_list"),
        "max_walking_km": inputs.get("max_walking_km"),
    }
    currency = str(inputs.get("currency", "USD"))
    audited = run_audit(plan, constraints, currency=currency, step_callback=step_callback)

    output: dict[str, Any] = audited.model_dump()

    # Dump for offline debugging — saves a re-run if anything downstream breaks.
    debug_path = Path("/tmp") / "crew_last_output.json"
    with contextlib.suppress(OSError):
        debug_path.write_text(json.dumps(output, indent=2))

    logger.info(
        "crew.run.success",
        extra={
            "days": len(output.get("days") or []),
            "approved": output.get("approved"),
            "revision_log_entries": len(output.get("revision_log") or []),
        },
    )
    client = get_langfuse()
    if client is not None:
        client.flush()
    return output


@observe(name="audit.loop")
def run_audit(
    plan: TripPlan,
    constraints: dict[str, Any],
    currency: str = "USD",
    step_callback: Callable[[Any], None] | None = None,
) -> AuditedPlan:
    """Run up to MAX_AUDIT_PASSES of the Budget Auditor over `plan`.

    Returns the last pass's AuditedPlan with the cumulative revision_log
    (each entry prefixed "Pass N: "). Returns immediately if a pass returns
    approved=true.
    """
    cumulative_log: list[str] = []
    current_plan = plan
    last_result: AuditedPlan | None = None

    for pass_num in range(1, MAX_AUDIT_PASSES + 1):
        last_result = _run_audit_pass(
            current_plan, constraints, currency, pass_num, step_callback=step_callback
        )
        cumulative_log.extend(f"Pass {pass_num}: {entry}" for entry in last_result.revision_log)
        if last_result.approved:
            break
        current_plan = TripPlan(days=last_result.days)

    assert last_result is not None  # MAX_AUDIT_PASSES >= 1 by construction
    return AuditedPlan(
        approved=last_result.approved,
        days=last_result.days,
        per_day_costs=last_result.per_day_costs,
        total_cost=last_result.total_cost,
        currency=last_result.currency or currency,
        constraints_violated=last_result.constraints_violated,
        explanation=last_result.explanation,
        revision_log=cumulative_log,
    )


@observe(name="audit.pass")
def _run_audit_pass(
    plan: TripPlan,
    constraints: dict[str, Any],
    currency: str,
    pass_num: int,
    step_callback: Callable[[Any], None] | None = None,
) -> AuditedPlan:
    """Single Auditor LLM call. Returns the AuditedPlan for THIS pass."""
    # Local import to avoid a researcher → tasks → budget_auditor → researcher
    # cycle when running stub tests that only need module-level objects.
    from trip_agents.budget_auditor import budget_auditor

    task = make_audit_task()
    crew_kwargs: dict[str, Any] = {
        "agents": [budget_auditor],
        "tasks": [task],
        "process": Process.sequential,
        "verbose": False,
    }
    if step_callback is not None:
        crew_kwargs["step_callback"] = step_callback
    crew = Crew(**crew_kwargs)
    pass_inputs: dict[str, Any] = {
        "current_plan_json": plan.model_dump_json(),
        "currency": currency,
        "budget_total": constraints.get("budget_total") or "unspecified",
        "per_day_budget": constraints.get("per_day_budget") or "unspecified",
        "dietary": constraints.get("dietary") or "none",
        "mobility": constraints.get("mobility") or "none",
        "no_go_list": constraints.get("no_go_list") or "none",
        "max_walking_km": constraints.get("max_walking_km") or "unspecified",
        "pass_num": pass_num,
    }
    logger.info("audit.pass.start", extra={"pass_num": pass_num})
    result = crew.kickoff(inputs=pass_inputs)
    if hasattr(result, "pydantic") and isinstance(result.pydantic, AuditedPlan):
        return result.pydantic
    # Fallback if structured output was not produced.
    parsed = _parse_json(str(result))
    if isinstance(parsed, dict):
        return AuditedPlan.model_validate(parsed)
    raise ValueError(
        f"audit pass {pass_num}: could not extract AuditedPlan from {str(result)[:200]!r}"
    )


def run_stub(destination: str) -> list[dict[str, Any]]:
    """Offline: return the slice-1.3 candidates fixture. Used by stub tests."""
    _ = destination
    data: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    return data


# Slice 3.3 commit 4: hierarchical refine + sequential single-day regenerate.


def _build_refine_crew(step_callback: Callable[[Any], None] | None = None) -> Crew:
    """Hierarchical 4-agent crew for refine_trip. manager_llm is REQUIRED by
    CrewAI for Process.hierarchical — we reuse build_llm() so the manager
    runs on the same Claude Sonnet 4 as the workers. Returns None in test
    contexts where ANTHROPIC_API_KEY is absent; tests mock the Crew
    constructor anyway so the None is invisible there.
    """
    from trip_agents.budget_auditor import budget_auditor  # noqa: PLC0415
    from trip_agents.llm import build_llm  # noqa: PLC0415

    refine_task = make_refine_task()
    kwargs: dict[str, Any] = {
        "agents": [researcher, local_expert, logistics_planner, budget_auditor],
        "tasks": [refine_task],
        "process": Process.hierarchical,
        "manager_llm": build_llm(),
        "verbose": False,
    }
    if step_callback is not None:
        kwargs["step_callback"] = step_callback
    return Crew(**kwargs)


@observe(name="crew.refine")
def refine(
    trip_state: dict[str, Any],
    refinement_description: str,
    step_callback: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    """Hierarchical refine. Returns AuditedPlan.model_dump() — same shape as
    plan_trip's output so the worker calls persist_audited_plan unchanged.
    """
    inputs: dict[str, Any] = {
        "trip_state_json": json.dumps(trip_state),
        "refinement_description": refinement_description,
    }
    logger.info("crew.refine.start", extra={"destination": trip_state.get("destination")})
    crew_result = _build_refine_crew(step_callback=step_callback).kickoff(inputs=inputs)
    audited = _extract_audited_plan(crew_result)
    output: dict[str, Any] = audited.model_dump()
    logger.info(
        "crew.refine.success",
        extra={"approved": output.get("approved"), "days": len(output.get("days") or [])},
    )
    return output


def _build_regenerate_day_crew(
    step_callback: Callable[[Any], None] | None = None,
) -> Crew:
    """Sequential 3-agent crew (Researcher → Local Expert → Logistics).
    Budget Auditor intentionally not included for single-day regen.
    """
    regen_task = make_regenerate_day_task()
    kwargs: dict[str, Any] = {
        "agents": [researcher, local_expert, logistics_planner],
        "tasks": [regen_task],
        "process": Process.sequential,
        "verbose": False,
    }
    if step_callback is not None:
        kwargs["step_callback"] = step_callback
    return Crew(**kwargs)


@observe(name="crew.regenerate_day")
def regenerate_day(
    trip_context: dict[str, Any],
    target_day: dict[str, Any],
    locked_blocks: list[dict[str, Any]],
    unlocked_positions: list[int],
    hint: str | None = None,
    step_callback: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    """Single-day regenerate. Returns a Day.model_dump() with blocks ONLY
    for the unlocked positions — worker splices locked blocks back in.
    """
    inputs: dict[str, Any] = {
        "trip_context_json": json.dumps(trip_context),
        "target_day_json": json.dumps(target_day),
        "locked_blocks_json": json.dumps(locked_blocks),
        "unlocked_positions": ", ".join(str(p) for p in unlocked_positions),
        "hint": hint or "no specific hint",
    }
    logger.info("crew.regenerate_day.start", extra={"day_number": target_day.get("day_number")})
    crew_result = _build_regenerate_day_crew(step_callback=step_callback).kickoff(inputs=inputs)
    day = _extract_day(crew_result)
    output: dict[str, Any] = day.model_dump()
    logger.info(
        "crew.regenerate_day.success",
        extra={"day_number": output.get("day_number"), "blocks": len(output.get("blocks") or [])},
    )
    return output


def _extract_audited_plan(crew_result: Any) -> AuditedPlan:
    """Pull an AuditedPlan from a Crew kickoff result — prefer .pydantic,
    fall back to JSON parsing.
    """
    pyd = getattr(crew_result, "pydantic", None)
    if isinstance(pyd, AuditedPlan):
        return pyd
    raw = getattr(crew_result, "raw", None) or str(crew_result)
    parsed = _parse_json(raw)
    if isinstance(parsed, dict):
        return AuditedPlan.model_validate(parsed)
    raise ValueError(f"could not extract AuditedPlan from {str(crew_result)[:200]!r}")


def _extract_day(crew_result: Any) -> Day:
    """Pull a Day from a Crew kickoff result."""
    pyd = getattr(crew_result, "pydantic", None)
    if isinstance(pyd, Day):
        return pyd
    raw = getattr(crew_result, "raw", None) or str(crew_result)
    parsed = _parse_json(raw)
    if isinstance(parsed, dict):
        return Day.model_validate(parsed)
    raise ValueError(f"could not extract Day from {str(crew_result)[:200]!r}")


def _extract_trip_plan(crew_result: Any) -> TripPlan:
    """Pull a TripPlan from a Crew kickoff result.

    Prefers .pydantic (set when output_pydantic= matched), falls back to
    parsing str(result) which may contain prose around the JSON.
    """
    if hasattr(crew_result, "pydantic") and isinstance(crew_result.pydantic, TripPlan):
        return crew_result.pydantic
    parsed = _parse_json(str(crew_result))
    if isinstance(parsed, list):
        parsed = {"days": parsed}
    if isinstance(parsed, dict):
        return TripPlan.model_validate(parsed)
    raise ValueError(f"could not extract TripPlan from {str(crew_result)[:200]!r}")


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


# Slice 3.4a commit 3: find_alternative — single-agent (Researcher) sequential
# crew that returns 3 ranked alternatives for one block. Option B from the
# file-tree session: Researcher alone for predictable wall time under the
# 90s route timeout. Local Expert addition tracked as trip-concierge-5yw.


def _build_find_alternative_crew(
    step_callback: Callable[[Any], None] | None = None,
) -> Crew:
    """Single-agent (Researcher) sequential crew for find_alternative.

    No manager_llm — sequential, not hierarchical. No Local Expert — the
    Researcher's prompt explicitly says "rank by fit to constraints",
    folding part of Local Expert's value into the Researcher prompt for
    predictable wall time.
    """
    task = make_find_alternative_task()
    kwargs: dict[str, Any] = {
        "agents": [researcher],
        "tasks": [task],
        "process": Process.sequential,
        "verbose": False,
    }
    if step_callback is not None:
        kwargs["step_callback"] = step_callback
    return Crew(**kwargs)


@observe(name="crew.find_alternative")
def find_alternative(
    trip_state: dict[str, Any],
    block: dict[str, Any],
    reason: str | None = None,
    step_callback: Callable[[Any], None] | None = None,
) -> dict[str, Any]:
    """Return AlternativesList.model_dump() with exactly 3 ranked alternatives.

    `trip_state` carries destination, currency, and constraints_summary.
    `block` carries the block being replaced: type, venue_name,
    duration_minutes, start_time. The route does the block_id → block
    lookup; this function receives the resolved block context so it stays
    a pure transform.

    Raises ValueError if the crew's output doesn't validate as a 3-item
    AlternativesList — the schema-layer enforcement of §3.7's "Return
    exactly 3 alternatives" instruction.
    """
    inputs: dict[str, Any] = {
        "destination": trip_state.get("destination", "unspecified"),
        "currency": trip_state.get("currency", "USD"),
        "constraints_summary": trip_state.get("constraints_summary", "none"),
        "block_type": block.get("type", "venue"),
        "block_venue_name": block.get("venue_name", "(unknown)"),
        "block_duration_minutes": block.get("duration_minutes", 60),
        "block_start_time": block.get("start_time") or "unspecified",
        "reason": reason or "(no reason given)",
    }
    logger.info(
        "crew.find_alternative.start",
        extra={"destination": inputs["destination"], "block_type": inputs["block_type"]},
    )
    crew_result = _build_find_alternative_crew(step_callback=step_callback).kickoff(inputs=inputs)
    alternatives_list = _extract_alternatives_list(crew_result)
    output: dict[str, Any] = alternatives_list.model_dump()
    logger.info(
        "crew.find_alternative.success",
        extra={"alternatives": len(output.get("alternatives") or [])},
    )
    return output


def _extract_alternatives_list(crew_result: Any) -> AlternativesList:
    """Pull AlternativesList from a CrewOutput. Prefers .pydantic (set when
    output_pydantic validation succeeded); falls back to JSON parsing the
    raw output. Raises ValueError on any failure so callers surface a
    clear error instead of silently shipping degraded output.
    """
    pyd = getattr(crew_result, "pydantic", None)
    if isinstance(pyd, AlternativesList):
        return pyd
    raw = getattr(crew_result, "raw", None) or str(crew_result)
    parsed = _parse_json(raw)
    if isinstance(parsed, dict):
        try:
            return AlternativesList.model_validate(parsed)
        except Exception as e:
            raise ValueError(
                f"AlternativesList validation failed: {e}. Raw: {str(raw)[:200]!r}"
            ) from e
    raise ValueError(
        f"AlternativesList could not be extracted from crew result: {str(crew_result)[:200]!r}"
    )
