"""arq worker for crew planning jobs.

Lives in backend (not agents) because it needs DB access — JobRun
inserts, Trip-day-block persistence. The opposite direction (worker in
agents importing backend models) would invert our workspace dep graph
and create a cycle.

Architecture: backend enqueues `plan_trip` jobs from POST /trips/{id}/plan
(slice 2.5c wiring); this worker process drains them, calls
trip_agents.crew.run, persists results via app.services.trip_service,
and writes one JobRun row per job.

Why arq and not Celery / RQ: see slice 2.5b architecture proposal.
Short version: asyncio-native, Redis-only, ~6k LOC, same author as
Pydantic. Right shape for our stack.

Retry policy is selective by exception class — see trip_agents.errors.
arq's default (`retries=5`, exponential backoff) would burn ~$1.50 of
Anthropic on a single bad-minute LLM API outage. We cap at 2 retries
on `RetryableJobError` (rate limits, transient 5xx) and zero retries
on `FatalJobError` (unparseable output, validation failures, cancel).

Per-agent observability lives in two places:
- Langfuse: the @observe decorators on crew.run / audit.loop / audit.pass
  already produce a trace tree per job. The worker doesn't double-trace.
- JobRun.agent_summary: a list[dict] populated via CrewAI's step_callback.
  Best-effort — if the LLM crashes mid-step we get partial data, which
  is still better than nothing for the "which agent failed?" question.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import litellm
from arq.connections import RedisSettings
from sqlalchemy.orm import Session
from trip_agents import crew as crew_module
from trip_agents.errors import FatalJobError, RetryableJobError

from app.config import settings
from app.db.session import get_session
from app.models.job_run import JobRun
from app.services.trip_service import persist_audited_plan

logger = logging.getLogger(__name__)

# Selective retry budget. Anthropic / Tavily 429s and transient 5xx warrant
# a retry; LLM-output parse failures and validation errors don't.
MAX_RETRIES = 2

# Job timeout — arq marks a job failed if the task doesn't return in this
# window. Generous because a 4-agent crew + 2 audit passes can take 12 min
# on a slow Anthropic minute.
JOB_TIMEOUT_SECONDS = 900  # 15 minutes


# Exception types that signal a transient infra problem regardless of any
# attribute on the exception — connect failures, read timeouts, etc.
# HTTPStatusError is NOT in this list because not all status codes are
# retryable (400, 404 must NOT be); see _is_retryable below.
_ALWAYS_RETRYABLE: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
)
# litellm has its own hierarchy; check for the ones that mean "try again later".
with contextlib.suppress(AttributeError):
    _ALWAYS_RETRYABLE = _ALWAYS_RETRYABLE + (
        litellm.exceptions.RateLimitError,
        litellm.exceptions.APIConnectionError,
        litellm.exceptions.ServiceUnavailableError,
        litellm.exceptions.Timeout,
    )

# HTTP status codes that warrant a retry. 429 = rate-limited; 502/503/504 =
# transient upstream failure. 4xx other than 429 means "your request is wrong"
# and retrying just re-burns tokens.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    """True iff this exception class signals a transient problem."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, _ALWAYS_RETRYABLE)


def _make_step_callback() -> tuple[list[dict[str, Any]], Any]:
    """Return (event_list, callback). The callback appends step events to
    the list as CrewAI fires them. We dump the list to JobRun.agent_summary
    when the job ends. Tolerant of unknown step shapes since CrewAI's
    callback contract has shifted across releases.
    """
    events: list[dict[str, Any]] = []
    started = time.monotonic()

    def cb(step: Any) -> None:
        entry: dict[str, Any] = {
            "event": type(step).__name__,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        # CrewAI step objects usually have `.agent` (with `.role`) and
        # `.output`. Be defensive — different CrewAI versions vary.
        agent = getattr(step, "agent", None)
        if agent is not None and hasattr(agent, "role"):
            entry["agent_role"] = agent.role
        output = getattr(step, "output", None)
        if output is not None:
            text = str(output)
            entry["output_excerpt"] = text[:200]
        events.append(entry)

    return events, cb


async def plan_trip(
    ctx: dict[str, Any],
    trip_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    """arq task: run the crew for a trip, persist results, write JobRun.

    `request` is the TripRunRequest dict captured at enqueue time. The
    worker MUST NOT re-read the Trip row — the snapshot is authoritative
    (slice 2.5b architecture decision).

    Returns the JobRun summary dict (suitable for arq's job result storage).
    Side effects: writes Trip Days/Blocks/Sources via persist_audited_plan,
    writes one JobRun row.
    """
    job_id = ctx.get("job_id", "unknown")
    started_at = datetime.now(UTC)
    monotonic_start = time.monotonic()

    events, cb = _make_step_callback()

    try:
        # The crew call dominates wall time. Run in the thread pool so the
        # arq event loop stays responsive (crew.run is sync under litellm).
        output = await asyncio.to_thread(
            crew_module.run,
            destination=request["destination"],
            step_callback=cb,
            **{k: v for k, v in request.items() if k != "destination"},
        )
    except asyncio.CancelledError:
        # User cancelled — write JobRun and re-raise so arq marks the job done.
        _write_job_run_session(
            job_id=str(job_id),
            trip_id=UUID(trip_id),
            status="cancelled",
            error="cancelled by user",
            agent_summary=events,
            started_at=started_at,
            monotonic_start=monotonic_start,
            total_cost=Decimal("0"),
            total_tokens=0,
        )
        raise
    except BaseException as exc:  # noqa: BLE001 — classify before re-raising
        if _is_retryable(exc):
            # Don't write a JobRun row — arq will retry. If we run out of
            # retries arq will eventually re-raise and the outer handler
            # writes the failed JobRun below.
            logger.warning(
                "plan_trip.retryable_error",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise RetryableJobError(str(exc)) from exc

        _write_job_run_session(
            job_id=str(job_id),
            trip_id=UUID(trip_id),
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            agent_summary=events,
            started_at=started_at,
            monotonic_start=monotonic_start,
            total_cost=Decimal("0"),
            total_tokens=0,
        )
        raise FatalJobError(str(exc)) from exc

    # Success path. Persist Days/Blocks/Sources to Postgres.
    db: Session
    db_iter = get_session()
    db = next(db_iter)
    try:
        persist_audited_plan(db, UUID(trip_id), output)
    finally:
        with contextlib.suppress(StopIteration):
            next(db_iter)

    job_run = _write_job_run_session(
        job_id=str(job_id),
        trip_id=UUID(trip_id),
        status="succeeded",
        error=None,
        agent_summary=events,
        started_at=started_at,
        monotonic_start=monotonic_start,
        # Token/cost rollup: parsing the per-step events for token deltas is
        # CrewAI-version-fragile. Slice 2.5c wires this properly via Langfuse
        # callbacks. For now, zero — the Langfuse trace is authoritative.
        total_cost=Decimal("0"),
        total_tokens=0,
    )
    return {
        "job_id": job_run.job_id,
        "trip_id": str(trip_id),
        "status": job_run.status,
        "approved": output.get("approved"),
    }


def _write_job_run_session(
    *,
    job_id: str,
    trip_id: UUID,
    status: str,
    error: str | None,
    agent_summary: list[dict[str, Any]],
    started_at: datetime,
    monotonic_start: float,
    total_cost: Decimal,
    total_tokens: int,
) -> Any:
    """Write a single JobRun row. Returns the persisted object.

    Factored out so the worker has one shape for success / failure / cancel.
    Uses backend's session factory so the connection picks up the same
    DATABASE_URL as the rest of the backend.
    """
    duration_ms = int((time.monotonic() - monotonic_start) * 1000)
    db_iter = get_session()
    db = next(db_iter)
    try:
        row = JobRun(
            job_id=job_id,
            trip_id=trip_id,
            status=status,
            error=error,
            agent_summary=agent_summary,
            total_tokens=total_tokens,
            total_cost=total_cost,
            total_duration_ms=duration_ms,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        with contextlib.suppress(StopIteration):
            next(db_iter)


class WorkerSettings:
    """arq WorkerSettings. Run with `arq app.worker.WorkerSettings`."""

    functions = [plan_trip]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4  # production cap; dev workers can override via env if needed
    job_timeout = JOB_TIMEOUT_SECONDS
    max_tries = MAX_RETRIES + 1  # arq counts the initial attempt
    keep_result = 3600  # 1h post-completion TTL on the Redis result entry
