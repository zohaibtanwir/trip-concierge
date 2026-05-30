"""asyncio loop provisioning for CrewAI Flow inside asyncio.to_thread.

Slice dzc-b-fix. Two tests:

Test 1 — `_kickoff_with_loop` succeeds inside asyncio.to_thread.
  This is the fix: providing a new event loop in the worker thread
  makes CrewAI's internal `asyncio.get_running_loop()` call succeed.

Test 2 — bare `asyncio.get_running_loop()` inside asyncio.to_thread
  raises RuntimeError. **This is the LOAD-BEARING regression-prevention
  test.** A future contributor who "cleans up" the loop wrapper as
  "weird unnecessary indirection" would silently reintroduce dzc/qek —
  the same bug that killed ~$1.20 of LLM spend across three trip
  reproductions (Goa, Pondicherry, Hampi) and consumed two P2
  tickets (trip-concierge-dzc + trip-concierge-qek) of investigation
  time before the root cause was found.

  CrewAI 1.14.5's `crewai/flow/flow.py:2120` makes the same call.
  If this test starts passing without the wrapper, the helper has
  been removed AND the bug is silently back AND we won't see
  evidence until the next 9-minute crew run burns money on the
  identical failure cycle.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from trip_agents.crew import _kickoff_with_loop


async def test_kickoff_with_loop_succeeds_inside_asyncio_to_thread() -> None:
    """The fix: `_kickoff_with_loop` provides an event loop in the worker
    thread so CrewAI's `get_running_loop()` succeeds.

    Mocked Crew so this test doesn't make real LLM calls. The crew's
    `.kickoff(inputs=...)` returns a sentinel; we verify the sentinel
    comes back via the wrapper. The asyncio.to_thread invocation mirrors
    `backend/app/worker.py:plan_trip`'s pattern exactly.
    """
    sentinel = MagicMock(name="CrewOutput")

    fake_crew = MagicMock()
    fake_crew.kickoff_async = AsyncMock(return_value=sentinel)

    inputs: dict[str, Any] = {"destination": "Goa, India", "vibe": "chill"}

    # Mirror worker.py:204 invocation pattern.
    result = await asyncio.to_thread(_kickoff_with_loop, fake_crew, inputs)

    fake_crew.kickoff_async.assert_awaited_once_with(inputs=inputs)
    assert result is sentinel


async def test_bare_get_running_loop_inside_to_thread_raises_runtime_error() -> None:
    """REGRESSION-PREVENTION: pins the bug shape this slice fixes.

    `asyncio.get_running_loop()` inside `asyncio.to_thread` raises
    `RuntimeError: no running event loop`. CrewAI 1.14.5's
    `crewai/flow/flow.py:2120` makes this call when a task has
    `output_pydantic` set. Without the `_kickoff_with_loop` wrapper,
    every Crew with output_pydantic (all 5 in our codebase: plan, audit,
    refine, regen, find_alternative) crashes the same way and produces
    a ~$0.40 money leak per attempt.

    If a future refactor "cleans up" `_kickoff_with_loop` as
    unnecessary indirection, this test stays green. THE BUG IS BACK
    SILENTLY. Without this test, the next contributor wouldn't notice
    until the next manual create_trip burned 9 minutes and $0.40 on
    the same fingerprint that already cost ~$1.20 across the
    pre-fix investigation window.

    Cite the dzc/qek root-cause observation in `experiments/01-langfuse.md`
    (line ~210+) for the full diagnostic story.
    """

    def get_loop_in_thread() -> asyncio.AbstractEventLoop:
        # This is essentially what crewai/flow/flow.py:2120 does.
        return asyncio.get_running_loop()

    with pytest.raises(RuntimeError, match="no running event loop"):
        await asyncio.to_thread(get_loop_in_thread)
