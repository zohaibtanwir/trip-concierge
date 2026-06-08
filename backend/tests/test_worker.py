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


class _FakeTaskOutput:
    """Mimics CrewAI's TaskOutput shape: .agent (str) + stringification.

    Path B (hotfix-kyh reframe 2026-06-08): CrewAI's TaskOutput passes
    the agent ROLE STRING via .agent (verified at
    crewai/tasks/task_output.py:42 — `agent: str`). The previous fakes
    passed bare strings to task_callback; the worker's task_cb didn't
    extract agent_role because the string had no .agent attribute.
    Path B fixes the extraction; this fake mirrors production shape so
    tests pin the contract end-to-end.
    """

    def __init__(self, agent_role: str, output: str) -> None:
        self.agent = agent_role
        self._output = output

    def __str__(self) -> str:
        return self._output


def _make_crew_run_that_fires_callback(output: dict[str, Any]):
    """Build a fake crew.run that invokes BOTH step_callback and
    task_callback. Path B: task_callback receives _FakeTaskOutput so the
    worker's agent_role extraction is exercised end-to-end.
    """

    def _crew_run(destination: str, step_callback=None, task_callback=None, **kwargs):  # noqa: ANN001
        if step_callback is not None:
            step_callback(_FakeStep("Travel Researcher", "found candidates"))
            step_callback(_FakeStep("Local Expert", "narrowed picks"))
            step_callback(_FakeStep("Logistics Planner", "built day-by-day plan"))
        if task_callback is not None:
            task_callback(_FakeTaskOutput("Travel Researcher", "research task complete"))
            task_callback(_FakeTaskOutput("Local Expert", "local-expert task complete"))
            task_callback(_FakeTaskOutput("Logistics Planner", "planning task complete"))
        return output

    return _crew_run


def _make_crew_run_that_fires_only_task_callback(output: dict[str, Any]):
    """Test A scenario — qek/kyh symptom replayed. step_callback path is
    silent (single-shot LLM outputs produce no intermediate steps), but
    task_callback fires once per task with the TaskOutput carrying the
    agent role. Path B's whole point: this scenario still produces
    useful agent attribution.
    """

    def _crew_run(destination: str, step_callback=None, task_callback=None, **kwargs):  # noqa: ANN001
        # step_callback NEVER fires — the kyh-reframe symptom.
        if task_callback is not None:
            task_callback(_FakeTaskOutput("Travel Researcher", "research task complete"))
            task_callback(_FakeTaskOutput("Local Expert", "local-expert task complete"))
            task_callback(_FakeTaskOutput("Logistics Planner", "planning task complete"))
        return output

    return _crew_run


def _make_crew_run_that_fires_nothing(output: dict[str, Any]):
    """Test C scenario — neither callback fires. The "we shipped the bug"
    state. agent_summary should still contain exactly one entry: the
    callback_summary entry with both counts at 0. Without that entry the
    "zero callbacks" signal is indistinguishable from "we forgot to
    append the summary."
    """

    def _crew_run(destination: str, step_callback=None, task_callback=None, **kwargs):  # noqa: ANN001
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

    # Filter-based assertions (slice qek-a discipline + Path B reframe) —
    # durable against adding more event types in future diagnostics. Path B
    # (2026-06-08): task_completed events now also carry agent_role, so
    # discriminate step vs task by `event` field rather than agent_role
    # presence.
    summary = job_run.agent_summary
    step_events = [
        e for e in summary if e.get("event") not in ("task_completed", "callback_summary")
    ]
    task_events = [e for e in summary if e.get("event") == "task_completed"]
    summary_events = [e for e in summary if e.get("event") == "callback_summary"]
    assert len(step_events) == 3, f"3 step events expected from 3 agents; got {summary}"
    assert len(task_events) == 3, f"3 task events expected from 3 tasks; got {summary}"
    assert len(summary_events) == 1, "exactly one callback_summary entry expected"

    roles = [e.get("agent_role") for e in step_events]
    assert "Travel Researcher" in roles
    assert "Logistics Planner" in roles

    # The callback_summary entry surfaces the counts the qek diagnostic
    # depends on. If step=0 in a real run, qek's failing-path is confirmed.
    assert summary_events[0]["step_callback_count"] == 3
    assert summary_events[0]["task_callback_count"] == 3

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
    # qek-a contract: even on the failure path the callback_summary
    # surfaces — counts are 0/0 because the crew raised before any
    # callback fired. Length-based assertion on this path is intentional;
    # zero-callback is the entire signal.
    summary = job_run.agent_summary
    assert len(summary) == 1
    assert summary[0]["event"] == "callback_summary"
    assert summary[0]["step_callback_count"] == 0
    assert summary[0]["task_callback_count"] == 0


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
    # qek-a contract: callback_summary lands even on the cancelled path.
    summary = added[0].agent_summary
    summary_events = [e for e in summary if e.get("event") == "callback_summary"]
    assert len(summary_events) == 1, "callback_summary must land on cancelled path too"


# ---------------------------------------------------------------------------
# Slice qek-a: 3 NEW tests pinning the shared-events closure contract.
# Test A and Test C are the load-bearers — Test A pins the "task_callback
# alone gives 3 events" scenario which may BE the qek fix; Test C pins the
# "zero callbacks → summary still surfaces zero counts" signal that qek-b
# will look for in real-worker run data.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_callback_alone_populates_agent_summary_when_step_callback_silent() -> None:
    """Test A — qek symptom replayed under qek-a contract.

    The hypothesis from qek investigation: under our CrewAI 1.14.5 config,
    step_callback never fires (~8 visible agent banners + agent_summary=[]
    in the production fingerprint). If task_callback fires per-task even
    when step_callback doesn't, this scenario shows agent_summary with 3
    task_completed entries + 1 callback_summary entry with counts (0, 3).

    This isn't just diagnostic — it's a workaround. If the next real run
    produces this shape, the slice ships qek with task_callback as the
    primary signal even before step_callback is repaired.
    """
    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(
        side_effect=_make_crew_run_that_fires_only_task_callback(_audited_plan_dict())
    )

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.persist_audited_plan"),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    summary = added[0].agent_summary

    # Discriminate step vs task by `event` field (Path B 2026-06-08:
    # task events also carry agent_role now, so the prior agent_role
    # presence filter would over-count).
    step_events = [
        e for e in summary if e.get("event") not in ("task_completed", "callback_summary")
    ]
    task_events = [e for e in summary if e.get("event") == "task_completed"]
    summary_events = [e for e in summary if e.get("event") == "callback_summary"]
    assert len(step_events) == 0, "step_callback path is silent — the qek/kyh symptom"
    assert len(task_events) == 3, "task_callback fires 3 times — Path B primary signal"
    assert len(summary_events) == 1
    assert summary_events[0]["step_callback_count"] == 0
    assert summary_events[0]["task_callback_count"] == 3

    # task_completed entries surface task index + timestamp + output excerpt
    # so qek-b can correlate against logs without re-running the crew.
    for idx, evt in enumerate(task_events, start=1):
        assert evt["task_index"] == idx
        assert "elapsed_ms" in evt
        assert "timestamp" in evt

    # Path B (hotfix-kyh reframe 2026-06-08): task_callback receives
    # CrewAI TaskOutput which carries .agent (role string). The worker
    # MUST extract that into agent_role on each task_completed event —
    # without it, the frontend can't show "Travel Researcher" as the
    # row title and falls back to literal "task_completed".
    expected_roles = ["Travel Researcher", "Local Expert", "Logistics Planner"]
    actual_roles = [evt.get("agent_role") for evt in task_events]
    assert actual_roles == expected_roles, (
        f"task_completed events must carry agent_role; got {actual_roles}"
    )


@pytest.mark.asyncio
async def test_both_callbacks_firing_reflects_real_counts_in_summary_entry() -> None:
    """Test B — happy state. Both callbacks fire (step 3x + task 3x).
    Summary entry surfaces the actual counts so the SQL post-mortem can
    distinguish 'partial firing' from 'no firing' even at a glance.
    """
    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(side_effect=_make_crew_run_that_fires_callback(_audited_plan_dict()))

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.persist_audited_plan"),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    summary = session_mock.add.call_args_list[0].args[0].agent_summary
    summary_events = [e for e in summary if e.get("event") == "callback_summary"]
    assert len(summary_events) == 1
    assert summary_events[0]["step_callback_count"] == 3
    assert summary_events[0]["task_callback_count"] == 3

    # Path B: both step + task events carry agent_role symmetrically.
    # Step events extract from _FakeStep.agent.role; task events extract
    # from _FakeTaskOutput.agent. Both should produce identical role
    # strings for the "everything works" demo state. The worker writes
    # type(step).__name__ as the `event` field; under the _FakeStep
    # fake that's "_FakeStep" (under real CrewAI it's "AgentFinish").
    # Filter by NOT-task-and-NOT-summary so the discriminator works
    # under both fake + real shapes.
    step_roles = [
        e.get("agent_role")
        for e in summary
        if e.get("event") not in ("task_completed", "callback_summary")
    ]
    task_roles = [e.get("agent_role") for e in summary if e.get("event") == "task_completed"]
    expected = ["Travel Researcher", "Local Expert", "Logistics Planner"]
    assert step_roles == expected, f"step_callback agent_role; got {step_roles}"
    assert task_roles == expected, f"task_callback agent_role; got {task_roles}"


@pytest.mark.asyncio
async def test_zero_callbacks_still_surfaces_summary_entry_with_both_counts_zero() -> None:
    """Test C — the load-bearer. The 'we shipped qek-a but the bug is
    even worse than expected' state: neither step_callback nor
    task_callback fires.

    Without the callback_summary entry, agent_summary would be empty —
    indistinguishable from 'we forgot to write the summary' or from
    'the worker crashed before assembling the JobRun'. The single
    callback_summary entry with (0, 0) is the unambiguous signal qek-b
    will look for in real production data.

    Length-based assertion is intentional here — the count IS the
    assertion. If agent_summary has anything OTHER than the summary
    entry, the slice's diagnostic contract is broken.
    """
    session_mock, session_iter = _patch_db_writes()
    crew_mock = MagicMock(side_effect=_make_crew_run_that_fires_nothing(_audited_plan_dict()))

    with (
        patch.object(worker.crew_module, "run", crew_mock),
        patch("app.worker.get_session", side_effect=session_iter),
        patch("app.worker.persist_audited_plan"),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    summary = session_mock.add.call_args_list[0].args[0].agent_summary
    assert len(summary) == 1, (
        f"agent_summary must contain exactly 1 entry (the callback_summary) "
        f"when neither callback fires; got {summary}"
    )
    entry = summary[0]
    assert entry["event"] == "callback_summary"
    assert entry["step_callback_count"] == 0
    assert entry["task_callback_count"] == 0


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
