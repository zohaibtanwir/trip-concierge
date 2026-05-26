"""Audit-loop orchestration tests.

These are pure-Python: they mock `_run_audit_pass` so no LLM call happens.
The contract verified here is the slice's "Done when" criterion — the
two-pass retry policy enforced in code, not in a prompt.
"""

from __future__ import annotations

from unittest.mock import patch

import crew as crew_mod
from schemas import AuditedPlan, Block, Day, TripPlan


def _plan() -> TripPlan:
    return TripPlan(
        days=[
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
    )


def _audited(
    approved: bool,
    revision_log: list[str],
    *,
    constraints_violated: list[str] | None = None,
    explanation: str = "",
) -> AuditedPlan:
    return AuditedPlan(
        approved=approved,
        days=_plan().days,
        per_day_costs=[1000.0],
        total_cost=1000.0,
        currency="USD",
        constraints_violated=constraints_violated or [],
        explanation=explanation,
        revision_log=revision_log,
    )


def test_pass_1_approved_returns_after_one_call() -> None:
    with patch.object(crew_mod, "_run_audit_pass") as m:
        m.return_value = _audited(True, ["cut block X"])
        result = crew_mod.run_audit(_plan(), constraints={}, currency="USD")
    assert m.call_count == 1
    assert result.approved is True
    assert result.revision_log == ["Pass 1: cut block X"]


def test_pass_1_fails_then_pass_2_approves() -> None:
    with patch.object(crew_mod, "_run_audit_pass") as m:
        m.side_effect = [
            _audited(False, ["compress day 2"]),
            _audited(True, ["swap restaurant"]),
        ]
        result = crew_mod.run_audit(_plan(), constraints={}, currency="USD")
    assert m.call_count == 2
    assert result.approved is True
    assert result.revision_log == [
        "Pass 1: compress day 2",
        "Pass 2: swap restaurant",
    ]


def test_both_passes_fail_returns_pass_2_with_approved_false() -> None:
    pass_2 = _audited(
        False,
        ["cut another"],
        constraints_violated=["total_budget"],
        explanation="over by 5000 INR",
    )
    with patch.object(crew_mod, "_run_audit_pass") as m:
        m.side_effect = [_audited(False, ["cut one"]), pass_2]
        result = crew_mod.run_audit(_plan(), constraints={}, currency="USD")
    assert m.call_count == 2
    assert result.approved is False
    assert result.constraints_violated == ["total_budget"]
    assert result.explanation == "over by 5000 INR"
    assert result.revision_log == ["Pass 1: cut one", "Pass 2: cut another"]


def test_orchestrator_caps_at_two_passes() -> None:
    """Even if every pass returns approved=False, the loop stops at MAX_AUDIT_PASSES."""
    with patch.object(crew_mod, "_run_audit_pass") as m:
        m.return_value = _audited(False, ["no-op"])
        crew_mod.run_audit(_plan(), constraints={}, currency="USD")
    assert m.call_count == crew_mod.MAX_AUDIT_PASSES == 2


def test_revised_plan_is_fed_forward_into_next_pass() -> None:
    """Pass 2 must receive Pass 1's revised plan, not the original."""
    pass_1 = _audited(False, ["dropped block 1"])
    # Pass 1's revised plan has zero cost so we can tell the days flowed through.
    pass_1 = AuditedPlan(
        approved=False,
        days=[
            Day(
                day_number=1,
                blocks=[
                    Block(
                        order=1,
                        type="venue",
                        venue_name="REVISED",
                        duration_minutes=30,
                    )
                ],
            )
        ],
        revision_log=["dropped block 1"],
    )
    pass_2 = _audited(True, ["ok"])
    calls: list[TripPlan] = []

    def _capture(plan, constraints, currency, pass_num):  # noqa: ANN001
        calls.append(plan)
        return [pass_1, pass_2][pass_num - 1]

    with patch.object(crew_mod, "_run_audit_pass", side_effect=_capture):
        crew_mod.run_audit(_plan(), constraints={}, currency="USD")

    assert len(calls) == 2
    # Pass 1 sees the original plan.
    assert calls[0].days[0].blocks[0].venue_name == "V1"
    # Pass 2 sees pass 1's revised plan.
    assert calls[1].days[0].blocks[0].venue_name == "REVISED"
