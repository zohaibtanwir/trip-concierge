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
from trip_agents.schemas import AuditedPlan, TripPlan
from trip_agents.tasks import (
    make_audit_task,
    make_local_expertise_task,
    make_planning_task,
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
