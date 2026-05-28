"""Plan endpoint schemas — Slice 2.5c.

Two distinct concepts on the status response:

- `state` is the **lifecycle** of the planning job (queued → running →
  done | failed | cancelled, with `cancelling` as a transient brake state
  during a DELETE race).
- `approved` is the **outcome** of the auditor — orthogonal to state.
  It's only meaningful when `state == "done"`:
    - state="done", approved=true  → crew finished, auditor approved
    - state="done", approved=false → crew finished cleanly but auditor
                                     returned approved=false (infeasible
                                     plan signal; the days/blocks rows
                                     exist but the client should warn)
    - any other state              → approved is null

Client polling pattern:
  while state not in {done, failed, cancelled}:
      sleep, poll
  branch on (state, approved)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PlanState = Literal["queued", "running", "cancelling", "done", "failed", "cancelled"]

# Slice 3.3: discriminates the in-flight job's type. 'plan' = create_trip's
# enqueued job, 'refine' = refine_trip's hierarchical job, 'regen' =
# regenerate_day's day-scoped job. Surfaces in the Redis active_job JSON and
# in PlanStatus.kind so the MCP get_trip tool can render kind-aware messages.
JobKind = Literal["plan", "refine", "regen"]


class ProgressUpdate(BaseModel):
    """Structured progress event written by the worker's step_callback.

    Stored as JSON at Redis key `trip:{trip_id}:progress`, replaced on each
    step. We keep this shape narrow on purpose — the PWA renders it directly
    and the (future) MCP tool emits it back to Claude Desktop. String
    flattening is the caller's job, not ours.

    `pass_` is aliased to `pass` (Python keyword) for the wire form.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    agent: str = Field(min_length=1, max_length=50)
    pass_: int = Field(alias="pass", ge=1, le=10)
    message: str = Field(max_length=200)


class PlanStatus(BaseModel):
    """GET /trips/{id}/plan/status response.

    See module docstring for the state vs approved distinction.
    """

    model_config = ConfigDict(populate_by_name=True)

    state: PlanState
    job_id: str | None = None
    # Slice 3.3: names the active job's kind when there is one. Null for
    # terminal states (those are recorded in JobRun.kind on the row instead).
    kind: JobKind | None = None
    approved: bool | None = None
    progress_message: ProgressUpdate | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    trip_url: str | None = None
