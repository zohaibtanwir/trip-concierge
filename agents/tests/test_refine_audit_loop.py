"""Refine audit-loop orchestration tests — slice 4.5b commit 1.

Mirror of test_audit_loop.py (plan_trip's Python-loop pattern) but for
the hierarchical refine flow. Per Q4=A sign-off: refine_trip honors
the PRD §F4 'max 2 retries' promise via a Python-side loop, not via
the manager_llm's soft prompt.

Current refine() (pre-4.5b): single hierarchical kickoff, returns
whatever the manager LLM produced. If approved=false, no retry —
PRD §F4 bullet 2 silently violated.

Post-4.5b: refine() runs the hierarchical kickoff once. If
approved=true, returns. Otherwise re-runs the Auditor (Python loop)
up to MAX_REFINE_AUDIT_PASSES additional passes. Mirror semantics:
each pass produces its own revision_log entries, concatenated with
'Pass N: ' prefix.

These tests are pure-Python — mock `_kickoff_with_loop` and
`_run_refine_audit_pass` so no LLM call happens. Contract verified:
code-level retry cap, not prompt-level.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import trip_agents.crew as crew_mod
from trip_agents.schemas import AuditedPlan, Block, Day


def _plan_days() -> list[Day]:
    return [
        Day(
            day_number=1,
            blocks=[
                Block(
                    order=1,
                    type="venue",
                    venue_name="V1",
                    duration_minutes=60,
                )
            ],
        )
    ]


def _audited(
    approved: bool,
    revision_log: list[str],
    *,
    constraints_violated: list[str] | None = None,
    explanation: str = "",
) -> AuditedPlan:
    return AuditedPlan(
        approved=approved,
        days=_plan_days(),
        per_day_costs=[1000.0],
        total_cost=1000.0,
        currency="USD",
        constraints_violated=constraints_violated or [],
        explanation=explanation,
        revision_log=revision_log,
    )


def _mock_crew_result(audited: AuditedPlan) -> MagicMock:
    """Shape a CrewOutput-like return value: .pydantic carries AuditedPlan."""
    result = MagicMock()
    result.pydantic = audited
    result.raw = audited.model_dump_json()
    return result


def test_max_refine_audit_passes_constant_exists() -> None:
    """The constant must live in crew.py alongside MAX_AUDIT_PASSES so
    future readers see the symmetric pattern. Value pinned at 2 per
    PRD §F4 bullet 2 'max 2 retries'."""
    assert hasattr(crew_mod, "MAX_REFINE_AUDIT_PASSES"), (
        "MAX_REFINE_AUDIT_PASSES must be defined in trip_agents.crew"
    )
    assert crew_mod.MAX_REFINE_AUDIT_PASSES == 2


def test_refine_returns_early_when_first_pass_approves() -> None:
    """Hierarchical kickoff returns approved=True → no audit loop runs.
    Same shape as plan_trip's run_audit early-exit."""
    trip_state = {"destination": "Coorg", "currency": "INR", "days": []}
    approved_result = _mock_crew_result(_audited(True, ["initial refine accepted"]))

    with (
        # _build_refine_crew constructs a hierarchical Crew which
        # CrewAI validates requires manager_llm. On CI, ANTHROPIC_API_KEY
        # is unset so build_llm() returns None and the Crew validator
        # would raise — even though _kickoff_with_loop is mocked. Patch
        # the crew builder too so construction never happens.
        patch.object(crew_mod, "_build_refine_crew", return_value=MagicMock()),
        patch.object(crew_mod, "_kickoff_with_loop", return_value=approved_result) as kickoff,
        patch.object(crew_mod, "_run_refine_audit_pass") as audit_pass,
    ):
        result = crew_mod.refine(trip_state, "make Day 2 chiller")

    assert kickoff.call_count == 1
    assert audit_pass.call_count == 0, "audit loop must not run when first pass approves"
    assert result["approved"] is True


def test_refine_runs_one_audit_pass_when_first_pass_fails_then_approves() -> None:
    """Hierarchical refine → approved=False. Audit pass 1 → approved=True.
    Total: 1 hierarchical kickoff + 1 audit pass = 2 LLM round-trips."""
    trip_state = {"destination": "Coorg", "currency": "INR", "days": []}
    failed_result = _mock_crew_result(
        _audited(False, ["over budget by 5000"], constraints_violated=["per_day_budget"])
    )
    approved_audit = _audited(True, ["compressed day 2"])

    with (
        patch.object(crew_mod, "_build_refine_crew", return_value=MagicMock()),
        patch.object(crew_mod, "_kickoff_with_loop", return_value=failed_result),
        patch.object(crew_mod, "_run_refine_audit_pass", return_value=approved_audit),
    ):
        result = crew_mod.refine(trip_state, "make Day 2 chiller")

    assert result["approved"] is True
    # revision_log should carry both the initial failed refine's entries
    # AND the audit-pass entries, with 'Pass N:' prefixes on the latter.
    assert any("compressed" in entry.lower() for entry in result["revision_log"])


def test_refine_caps_at_max_refine_audit_passes() -> None:
    """Both audit passes return approved=False. The loop stops at
    MAX_REFINE_AUDIT_PASSES — does not run a third pass.

    Final result: approved=False, plan reflects the LAST audit pass's
    output (closest feasible). UI surfaces this honestly."""
    trip_state = {"destination": "Coorg", "currency": "INR", "days": []}
    failed_result = _mock_crew_result(
        _audited(False, ["initial over budget"], constraints_violated=["per_day_budget"])
    )

    audit_call_count = 0

    def always_fail(*_args, **_kwargs) -> AuditedPlan:
        nonlocal audit_call_count
        audit_call_count += 1
        return _audited(
            False,
            [f"pass {audit_call_count} could not fit"],
            constraints_violated=["per_day_budget"],
            explanation="over by 3000 INR",
        )

    with (
        patch.object(crew_mod, "_build_refine_crew", return_value=MagicMock()),
        patch.object(crew_mod, "_kickoff_with_loop", return_value=failed_result),
        patch.object(crew_mod, "_run_refine_audit_pass", side_effect=always_fail),
    ):
        result = crew_mod.refine(trip_state, "redo with tight budget")

    assert audit_call_count == crew_mod.MAX_REFINE_AUDIT_PASSES == 2
    assert result["approved"] is False
    assert result["constraints_violated"] == ["per_day_budget"]
    assert result["explanation"]


def test_refine_revision_log_concat_uses_pass_prefix() -> None:
    """Each audit pass's entries get a 'Pass N: ' prefix in the cumulative
    log — mirror of run_audit's existing concatenation pattern."""
    trip_state = {"destination": "Coorg", "currency": "INR", "days": []}
    failed_result = _mock_crew_result(_audited(False, ["initial fail"]))
    pass_1 = _audited(False, ["cut block X"])
    pass_2 = _audited(True, ["swap restaurant"])

    with (
        patch.object(crew_mod, "_build_refine_crew", return_value=MagicMock()),
        patch.object(crew_mod, "_kickoff_with_loop", return_value=failed_result),
        patch.object(crew_mod, "_run_refine_audit_pass", side_effect=[pass_1, pass_2]),
    ):
        result = crew_mod.refine(trip_state, "tighten budget")

    log = result["revision_log"]
    assert any("Pass 1:" in entry and "cut block X" in entry for entry in log)
    assert any("Pass 2:" in entry and "swap restaurant" in entry for entry in log)


@pytest.mark.parametrize(
    "constraints_summary",
    [
        {"per_day_budget": "5000", "max_walking_km": "5", "currency": "INR"},
        {"per_day_budget": None, "max_walking_km": "10"},
    ],
)
def test_refine_passes_constraints_to_audit_pass(constraints_summary: dict) -> None:
    """The constraints dict (per_day_budget, max_walking_km, etc.) must
    flow from trip_state through refine() into _run_refine_audit_pass.
    Verifies the Q3=A flat-fields-on-trip_state propagation reaches
    the audit task template variables."""
    trip_state = {
        "destination": "Coorg",
        "currency": constraints_summary.get("currency", "INR"),
        "days": [],
        **{k: v for k, v in constraints_summary.items() if k != "currency"},
    }
    failed_result = _mock_crew_result(_audited(False, ["initial fail"]))

    captured_constraints: dict = {}

    def capture_call(plan, constraints, currency, pass_num, **_kwargs) -> AuditedPlan:
        captured_constraints.update(constraints)
        return _audited(True, ["done"])

    with (
        patch.object(crew_mod, "_build_refine_crew", return_value=MagicMock()),
        patch.object(crew_mod, "_kickoff_with_loop", return_value=failed_result),
        patch.object(crew_mod, "_run_refine_audit_pass", side_effect=capture_call),
    ):
        crew_mod.refine(trip_state, "test refinement")

    # The audit pass should see the per_day_budget + max_walking_km
    # values pulled from trip_state.
    assert "per_day_budget" in captured_constraints
    assert "max_walking_km" in captured_constraints
