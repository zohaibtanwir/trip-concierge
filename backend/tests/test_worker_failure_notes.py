"""Worker propagates exc.__notes__ into JobRun.error (slice dzc-a).

The dzc-a contract has two ends:
  1. agents/crew.py adds a `failure dump: <path>` note to the
     exception via Python 3.11's exc.add_note() when extraction
     fails — pinned by test_crew_failure_dump.py.
  2. backend/worker.py reads exc.__notes__ in the fatal-path
     handler and appends them to the JobRun.error string on a
     fresh line — pinned here.

Without (2), the dump path lands on disk but never reaches the DB,
and a post-mortem SQL query against job_runs.error misses the
pointer to the artifact we need to actually diagnose the bug.

slice-3.3 _categorize_error() in mcp_server/_responses.py splits
JobRun.error on the FIRST colon to recover the class name. Appending
notes AFTER the existing "ClassName: message" text doesn't disrupt
that — the colon-split still recovers "ValidationError" or
"ValueError" cleanly. Property pinned by checking that the error
string starts with the class name AND the note line appears later.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from trip_agents.errors import FatalJobError

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


def _patch_db_writes() -> tuple[MagicMock, Any]:
    session_mock = MagicMock()

    def _session_iter():
        yield session_mock

    return session_mock, _session_iter


@pytest.mark.asyncio
async def test_worker_propagates_failure_dump_note_into_job_run_error() -> None:
    """Replays the dzc-a end-to-end contract: crew raises with a
    `failure dump: <path>` note attached; worker writes a JobRun
    whose .error contains both the original exception text AND the
    note on a fresh line.
    """
    session_mock, session_iter = _patch_db_writes()

    def _crew_run_that_fails(destination: str, step_callback=None, **kwargs):  # noqa: ANN001, ARG001
        exc = ValueError("could not extract TripPlan from '{}' (parsed to empty dict)")
        # The note dzc-a's crew.py will attach in production.
        exc.add_note("failure dump: /tmp/crew_failure_20260530T143500Z.json")
        raise exc

    with (
        patch.object(worker.crew_module, "run", _crew_run_that_fails),
        patch("app.worker.get_session", side_effect=session_iter),
        pytest.raises(FatalJobError),
    ):
        await worker.plan_trip(_ctx(), str(uuid.uuid4()), _request())

    added = [c.args[0] for c in session_mock.add.call_args_list]
    assert len(added) == 1
    job_run = added[0]
    assert job_run.status == "failed"

    # Both ends present in the error column.
    err = job_run.error or ""
    assert err.startswith("ValueError:"), (
        f"class name prefix must be preserved for slice-3.3 _categorize_error "
        f"colon-split; got {err[:80]!r}"
    )
    assert "could not extract TripPlan" in err
    assert "failure dump:" in err
    assert "crew_failure_20260530T143500Z.json" in err

    # Note lands on its own line so SQL `LIKE '%failure dump:%'`
    # post-mortems can extract the path without parsing the original
    # exception message.
    lines = err.splitlines()
    note_line_present = any(line.startswith("failure dump:") for line in lines)
    assert note_line_present, (
        f"the failure-dump note must appear on its own line; got lines={lines!r}"
    )
