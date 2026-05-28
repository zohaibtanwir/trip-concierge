"""Direct-call tests for trip_agents.worker.plan_trip.

No real queue, no real LLM, no real Redis. We call the task function
directly with a fake `ctx`, mock crew.run + persist_audited_plan + the
DB session, and verify the four terminal states behave correctly:

1. success → JobRun row written with status=succeeded, agent_summary
   populated by step_callback events
2. fatal error → JobRun row written with status=failed, error captured;
   FatalJobError is raised
3. retryable error (httpx 429) → no JobRun row written (arq will retry);
   RetryableJobError is raised
4. cancellation → JobRun row written with status=cancelled;
   CancelledError re-raised so arq marks the job done

The test patches `trip_agents.crew.run` — same path the agents service
patches in slice 2.5a's integration test. Get it wrong and the real
LLM gets called. The assertion `crew_mock.called` is the load-bearing
guard.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from trip_agents.errors import FatalJobError, RetryableJobError

from app import worker


def _ctx(job_id: str = "deadbeef") -> dict[str, Any]:
    return {"job_id": job_id}


def _request() -> dict[str, Any]:
    return {
        "destination": "Goa, India",
        "start_date": "2026-07-01",
        "end_date": "2026-07-03",
        "budget_total": 40000,
        "currency": "INR",
        "vibe": "chill",
        "group_size": 2,
        "pace": "balanced",
    }


def _audited_plan_dict() -> dict[str, Any]:
    return {
        "approved": True,
        "currency": "INR",
        "total_cost": 25000.0,
        "per_day_costs": [25000.0],
        "constraints_violated": [],
        "explanation": "",
        "revision_log": ["Pass 1: nothing to revise"],
        "days": [
            {
                "day_number": 1,
                "date": "2026-07-01",
                "summary": "Test",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Test Venue",
                        "start_time": "09:00",
                        "duration_minutes": 60,
                        "est_cost": 25000.0,
                        "currency": "INR",
                        "source_urls": ["https://example.com"],
                    }
                ],
            }
        ],
    }


class _FakeStep:
    """Mimics CrewAI's step-callback object shape: .agent.role + .output."""

    def __init__(self, role: str, output: str) -> None:
        self.agent = type("Agent", (), {"role": role})()
        self.output = output


def _make_crew_run_that_fires_callback(output: dict[str, Any]):
    """Build a fake crew.run that invokes the step_callback before returning."""

    def _crew_run(destination: str, step_callback=None, **kwargs):  # noqa: ANN001
        if step_callback is not None:
            step_callback(_FakeStep("Travel Researcher", "found candidates"))
            step_callback(_FakeStep("Local Expert", "narrowed picks"))
            step_callback(_FakeStep("Logistics Planner", "built day-by-day plan"))
        return output

    return _crew_run


def _patch_db_writes():
    """Patch get_session + persist_audited_plan so tests don't hit Postgres.

    Returns a MagicMock for the JobRun rows that get added to the session,
    so each test can assert what status/error/agent_summary was written.
    """
    session_mock = MagicMock()

    def _session_iter():
        yield session_mock

    return session_mock, _session_iter


@pytest.mark.asyncio
async def test_success_writes_job_run_with_agent_summary() -> None:
    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(side_effect=_make_crew_run_that_fires_callback(_audited_plan_dict()))

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.persist_audited_plan") as persist_mock,
    ):
        result = await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    assert crew_mock.called, (
        "crew.run was not invoked — patch target may be wrong (real LLM could be called)"
    )
    assert persist_mock.called, "persist_audited_plan should run on the success path"

    # Worker called session_mock.add(JobRun(...)) exactly twice: once never —
    # actually once on the success path. Inspect the JobRun argument.
    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    job_run = added[0]
    assert job_run.status == "succeeded"
    assert job_run.error is None
    # step_callback fired three times for the three crew agents.
    assert len(job_run.agent_summary) == 3
    roles = [e.get("agent_role") for e in job_run.agent_summary]
    assert "Travel Researcher" in roles
    assert "Logistics Planner" in roles

    assert result["status"] == "succeeded"
    assert result["approved"] is True


@pytest.mark.asyncio
async def test_fatal_error_writes_failed_job_run() -> None:
    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(side_effect=ValueError("unparseable LLM output"))

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        pytest.raises(FatalJobError, match="unparseable LLM output"),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    job_run = added[0]
    assert job_run.status == "failed"
    assert "unparseable LLM output" in (job_run.error or "")


@pytest.mark.asyncio
async def test_retryable_error_writes_no_job_run() -> None:
    """httpx 429 → RetryableJobError; arq will retry; no JobRun yet."""
    session_mock, session_iter = _patch_db_writes()
    response = httpx.Response(429, request=httpx.Request("GET", "https://api.anthropic.com"))
    crew_mock = MagicMock(
        side_effect=httpx.HTTPStatusError("429", request=response.request, response=response)
    )

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        pytest.raises(RetryableJobError),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    assert not session_mock.add.called, (
        "Retryable errors must not write JobRun — arq will retry; "
        "the row gets written only on a terminal outcome."
    )


@pytest.mark.asyncio
async def test_cancellation_writes_cancelled_job_run() -> None:
    """asyncio.CancelledError → JobRun status=cancelled, re-raised for arq."""
    import asyncio

    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(side_effect=asyncio.CancelledError())

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        pytest.raises(asyncio.CancelledError),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    assert added[0].status == "cancelled"
    assert "cancelled" in (added[0].error or "").lower()


def test_is_retryable_classifies_429_and_5xx() -> None:
    """Pure-function check on the retry classifier."""
    request = httpx.Request("GET", "https://x.test")

    def _err(code: int) -> httpx.HTTPStatusError:
        return httpx.HTTPStatusError(
            str(code), request=request, response=httpx.Response(code, request=request)
        )

    assert worker._is_retryable(_err(429))
    assert worker._is_retryable(_err(503))
    assert not worker._is_retryable(_err(400))
    assert not worker._is_retryable(_err(404))
    assert not worker._is_retryable(ValueError("nope"))
    assert worker._is_retryable(httpx.ConnectError("network down"))


# ---------------------------------------------------------------------------
# Slice 3.3 commit 4: refine_trip and regenerate_day workers wired to real
# crew functions + persistence. Tests mock the crew at the worker boundary
# (same pattern as plan_trip mocking crew_module.run), plus mock the
# DB-loading and persistence helpers since this file uses _patch_db_writes
# (session-level mock, not real DB).
# ---------------------------------------------------------------------------


def _fake_trip_with_blocks(
    locked_orders: tuple[int, ...] = (), all_orders: tuple[int, ...] = (1, 2, 3)
) -> MagicMock:
    """Build a MagicMock Trip with one Day whose blocks have specified
    `order` values and locked flags. Used by worker tests that need the
    Trip ORM-object shape (not real DB rows)."""
    blocks = []
    for o in all_orders:
        b = MagicMock()
        b.order = o
        b.locked = o in locked_orders
        b.type = "venue"
        b.venue_name = f"V{o}{'-LOCKED' if b.locked else ''}"
        b.duration_minutes = 60
        b.est_cost = None
        b.currency = "INR"
        b.lat = None
        b.lng = None
        b.start_time = None
        b.notes = ""
        b.sources = []
        blocks.append(b)
    day = MagicMock()
    day.day_number = 1
    day.date = None
    day.summary = "Day 1"
    day.blocks = blocks
    trip = MagicMock()
    trip.destination = "Goa, India"
    trip.currency = "INR"
    trip.budget_total = None
    trip.group_size = 1
    trip.pace = "balanced"
    trip.days = [day]
    return trip


@pytest.mark.asyncio
async def test_refine_trip_loads_state_passes_dict_persists_and_writes_kind_refine() -> None:
    """Happy path: load trip → call crew.refine(trip_state, refinement) →
    persist AuditedPlan → write JobRun(kind='refine'). Verify the dict
    shape that reaches the crew so the crew test contract is preserved."""
    session_mock, session_iter = _patch_db_writes()
    fake_trip = _fake_trip_with_blocks()
    audited = {"approved": True, "days": [], "revision_log": []}
    crew_mock = MagicMock(return_value=audited)

    with (
        patch.object(worker.crew_module, "refine", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.get_trip_full", return_value=fake_trip),
        patch("app.worker.persist_audited_plan") as persist_mock,
    ):
        result = await worker.refine_trip(_ctx(), str(uuid.uuid4()), "make it chiller")

    assert crew_mock.called, "crew.refine not invoked — patch target may be wrong"
    # The trip_state arg the crew receives must include destination + days.
    call_kwargs = crew_mock.call_args.kwargs
    assert "trip_state" in call_kwargs, "crew.refine must receive trip_state kwarg"
    trip_state = call_kwargs["trip_state"]
    assert trip_state["destination"] == "Goa, India"
    assert isinstance(trip_state["days"], list) and len(trip_state["days"]) == 1
    assert call_kwargs["refinement_description"] == "make it chiller"

    assert persist_mock.called, "persist_audited_plan must run on success"
    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    assert added[0].kind == "refine"
    assert added[0].status == "succeeded"
    assert result["status"] == "succeeded"


@pytest.mark.asyncio
async def test_refine_trip_fatal_error_writes_failed_with_kind_refine() -> None:
    """Crew raises → FatalJobError + JobRun(status='failed', kind='refine')."""
    session_mock, session_iter = _patch_db_writes()
    fake_trip = _fake_trip_with_blocks()
    crew_mock = MagicMock(side_effect=ValueError("unparseable refine output"))

    with (
        patch.object(worker.crew_module, "refine", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.get_trip_full", return_value=fake_trip),
        pytest.raises(FatalJobError, match="unparseable refine output"),
    ):
        await worker.refine_trip(_ctx(), str(uuid.uuid4()), "anything")

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    assert added[0].kind == "refine"
    assert added[0].status == "failed"


@pytest.mark.asyncio
async def test_regenerate_day_filters_locked_blocks_and_splices_result() -> None:
    """The load-bearing locked-block test. Trip Day 1 has blocks at orders
    1, 2, 3 with block 2 locked. The worker:
    1. Pre-filters: only positions 1 and 3 are sent to the crew.
    2. Crew returns blocks for those positions only (mocked).
    3. Worker splices the locked block 2 back in.
    4. persist_regenerated_day receives all 3 blocks in order.
    """
    session_mock, session_iter = _patch_db_writes()
    fake_trip = _fake_trip_with_blocks(locked_orders=(2,), all_orders=(1, 2, 3))
    # Crew returns Day dict with blocks for the unlocked positions only.
    crew_mock = MagicMock(
        return_value={
            "day_number": 1,
            "date": None,
            "summary": "Day 1",
            "blocks": [
                {"order": 1, "type": "venue", "venue_name": "NEW-1", "duration_minutes": 60},
                {"order": 3, "type": "venue", "venue_name": "NEW-3", "duration_minutes": 60},
            ],
        }
    )

    with (
        patch.object(worker.crew_module, "regenerate_day", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.get_trip_full", return_value=fake_trip),
        patch("app.worker.persist_regenerated_day") as persist_mock,
    ):
        await worker.regenerate_day(_ctx(), str(uuid.uuid4()), 1, "more food")

    # Crew received only the unlocked positions.
    call_kwargs = crew_mock.call_args.kwargs
    assert "unlocked_positions" in call_kwargs
    assert sorted(call_kwargs["unlocked_positions"]) == [1, 3], (
        "locked block at position 2 must not be in unlocked_positions"
    )
    assert "locked_blocks" in call_kwargs
    locked = call_kwargs["locked_blocks"]
    assert len(locked) == 1 and locked[0]["order"] == 2

    # persist_regenerated_day got all 3 spliced blocks in order.
    persist_call = persist_mock.call_args
    spliced = persist_call.kwargs.get("blocks") or persist_call.args[-1]
    assert [b["order"] for b in spliced] == [1, 2, 3], (
        "spliced blocks must include the locked block at its original position"
    )
    # The block at order=2 is the LOCKED one.
    block_at_2 = next(b for b in spliced if b["order"] == 2)
    assert "LOCKED" in block_at_2["venue_name"], (
        "spliced block at position 2 must be the original locked block, not a regenerated one"
    )


@pytest.mark.asyncio
async def test_regenerate_day_fatal_error_writes_failed_with_kind_regen() -> None:
    session_mock, session_iter = _patch_db_writes()
    fake_trip = _fake_trip_with_blocks()
    crew_mock = MagicMock(side_effect=ValueError("crew blew up"))

    with (
        patch.object(worker.crew_module, "regenerate_day", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.get_trip_full", return_value=fake_trip),
        pytest.raises(FatalJobError, match="crew blew up"),
    ):
        await worker.regenerate_day(_ctx(), str(uuid.uuid4()), 1)

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    assert added[0].kind == "regen"
    assert added[0].status == "failed"
