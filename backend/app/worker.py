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
import json
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
from app.schemas.plan import ProgressUpdate
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


def _make_step_callback(
    redis: Any | None = None,
    trip_id: str | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[list[dict[str, Any]], Any]:
    """Return (event_list, callback). The callback appends step events to
    the list as CrewAI fires them. We dump the list to JobRun.agent_summary
    when the job ends. Tolerant of unknown step shapes since CrewAI's
    callback contract has shifted across releases.

    If `redis`, `trip_id`, and `loop` are all provided, the callback also
    writes a ProgressUpdate JSON to `trip:{trip_id}:progress` — the status
    endpoint reads this. Best-effort: a Redis failure must not fail the job.

    `loop` must be the running asyncio loop captured before entering
    `asyncio.to_thread`. The callback runs on a worker thread (no loop of
    its own), so we bridge via `run_coroutine_threadsafe`.
    """
    events: list[dict[str, Any]] = []
    started = time.monotonic()
    progress_key = f"trip:{trip_id}:progress" if (redis is not None and trip_id and loop) else None

    def cb(step: Any) -> None:
        entry: dict[str, Any] = {
            "event": type(step).__name__,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        agent = getattr(step, "agent", None)
        agent_role = None
        if agent is not None and hasattr(agent, "role"):
            agent_role = agent.role
            entry["agent_role"] = agent_role
        output = getattr(step, "output", None)
        if output is not None:
            text = str(output)
            entry["output_excerpt"] = text[:200]
        events.append(entry)

        if progress_key and agent_role:
            pass_num = getattr(step, "pass_num", None) or 1
            try:
                # Build via dict + model_validate so the field alias `pass`
                # (a Python keyword) is the wire form. populate_by_name=True
                # also accepts pass_ as the kwarg, but mypy doesn't track
                # pydantic aliases — the dict path is unambiguous.
                payload = ProgressUpdate.model_validate(
                    {
                        "agent": agent_role[:50],
                        "pass": int(pass_num),
                        "message": (
                            str(output)[:200] if output is not None else f"{agent_role} step"
                        ),
                    }
                ).model_dump(by_alias=True)
                assert loop is not None and redis is not None
                asyncio.run_coroutine_threadsafe(
                    redis.setex(progress_key, _PROGRESS_TTL_SECONDS, json.dumps(payload)),
                    loop,
                )
            except Exception:
                # Progress is observability, not correctness. Never kill the job.
                logger.debug("plan.progress_write.skipped", exc_info=True)

    return events, cb


# Progress key TTL — short. The status endpoint reads it best-effort; a
# worker crash should not leave stale progress visible for long.
_PROGRESS_TTL_SECONDS = 120


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

    # arq passes the ArqRedis pool to tasks via ctx["redis"]. Capture the
    # running loop here (the only thread that owns it) so the step_callback
    # can schedule writes from inside asyncio.to_thread.
    redis = ctx.get("redis")
    loop = asyncio.get_running_loop()
    events, cb = _make_step_callback(redis=redis, trip_id=trip_id, loop=loop)

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
        # User cancelled — write JobRun, clean up DELETE's tombstone and
        # active_job key, re-raise so arq marks the job done.
        _write_job_run_session(
            job_id=str(job_id),
            trip_id=UUID(trip_id),
            status="cancelled",
            approved=None,
            error="cancelled by user",
            agent_summary=events,
            started_at=started_at,
            monotonic_start=monotonic_start,
            total_cost=Decimal("0"),
            total_tokens=0,
        )
        await _cleanup_redis_keys(redis, trip_id, include_cancelling=True)
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
            approved=None,
            error=f"{type(exc).__name__}: {exc}",
            agent_summary=events,
            started_at=started_at,
            monotonic_start=monotonic_start,
            total_cost=Decimal("0"),
            total_tokens=0,
        )
        await _cleanup_redis_keys(redis, trip_id, include_cancelling=False)
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

    approved = bool(output.get("approved")) if "approved" in output else None
    job_run = _write_job_run_session(
        job_id=str(job_id),
        trip_id=UUID(trip_id),
        status="succeeded",
        approved=approved,
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
    await _cleanup_redis_keys(redis, trip_id, include_cancelling=False)
    return {
        "job_id": job_run.job_id,
        "trip_id": str(trip_id),
        "status": job_run.status,
        "approved": approved,
    }


def _write_job_run_session(
    *,
    job_id: str,
    trip_id: UUID,
    status: str,
    approved: bool | None,
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
            approved=approved,
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


async def _cleanup_redis_keys(redis: Any | None, trip_id: str, *, include_cancelling: bool) -> None:
    """Best-effort cleanup of slice-2.5c Redis keys on terminal events.

    The status endpoint resolves terminal state from JobRun, so leaving
    keys with TTL would also work — but explicit cleanup keeps the
    invariant simple: post-terminal, there are no `trip:{id}:*` keys.

    `include_cancelling=True` on the cancellation path so the GET handler
    stops returning state="cancelling" the moment the JobRun row exists.
    """
    if redis is None:
        return
    keys = [f"trip:{trip_id}:active_job", f"trip:{trip_id}:progress"]
    if include_cancelling:
        keys.append(f"trip:{trip_id}:cancelling")
    with contextlib.suppress(Exception):
        await redis.delete(*keys)


class WorkerSettings:
    """arq WorkerSettings. Run with `arq app.worker.WorkerSettings`."""

    functions = [plan_trip]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4  # production cap; dev workers can override via env if needed
    job_timeout = JOB_TIMEOUT_SECONDS
    max_tries = MAX_RETRIES + 1  # arq counts the initial attempt
    keep_result = 3600  # 1h post-completion TTL on the Redis result entry
