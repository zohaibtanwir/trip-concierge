"""POST /trips/{trip_id}/blocks/{block_id}/alternative — synchronous
crew call returning 3 ranked AlternativesList items inline.

Slice 3.4a commit 4. Unlike POST /plan, /refine, /regenerate (which
enqueue arq jobs and return 202), this route runs the find_alternative
crew INSIDE the request thread, gated by a 90s asyncio.wait_for
timeout. Rationale:

- find_alternative is a small, focused crew (Researcher alone, single
  pass). Wall-time p99 is well under 90s by design.
- Returning alternatives async-via-arq would force the MCP host to
  poll, which wastes Claude Desktop turns. Synchronous keeps the
  user's turn coherent: one tool call → 3 alternatives → render.
- The 90s timeout is a hard ceiling, not a soft target. If the crew
  takes longer, we surface 504 with a structured body so the MCP
  tool can render a clean "try again" message.

Gate ordering (top to bottom, fail-fast):

1. Auth — Depends(require_mcp_token); 401 if missing/bad.
2. Trip exists — 404 if Trip.id not found.
3. Active job in flight — 409 + kind="active_job" + job_id + kind label.
   Reuses slice-3.3 decode_active_value + KIND_LABELS from app.routes.plan.
4. Trip in succeeded state — checks latest JobRun.status; 409 +
   kind="not_ready" + state if never planned, failed, or cancelled.
5. block_id exists on this trip — 404 if not. Backend layer of the
   UUID-hallucination defense (schema + prompt layers live in agents/).
6. Crew call — asyncio.wait_for(asyncio.to_thread(find_alternative,
   ...), timeout=90.0).
7. Timeout — catch asyncio.TimeoutError; return 504 + kind="timeout".
8. Success — 200 + AlternativesList.model_dump().

The 409 body shape is consistent across kinds:
  {"detail": "...", "kind": "active_job"|"not_ready", ...metadata...}
The MCP tool branches on `kind`, not on the status code or detail string.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from trip_agents.crew import find_alternative

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.user import User
from app.routes.plan import KIND_LABELS, decode_active_value
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["alternative"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]

# Hard wall-clock ceiling for the synchronous crew call. See module
# docstring for rationale; see commit message for the v1.0 cost-leak
# limitation (Python can't cancel running threads).
_FIND_ALTERNATIVE_TIMEOUT_SECONDS = 90.0


class AlternativeRequest(BaseModel):
    """POST /trips/{id}/blocks/{block_id}/alternative body."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional free-text reason for the swap (e.g., 'closed for "
            "renovations', 'budget too high'). Passed to the crew as "
            "ranking context; does not affect schema validation."
        ),
    )


def _constraints_summary(constraints: dict[str, Any] | None) -> str:
    """Flatten Trip.constraints["rules"] into a single string for the
    crew prompt. The crew prompt template uses this verbatim — it's
    the source of truth for "what the user has told us so far."
    """
    if not constraints:
        return "none"
    rules = constraints.get("rules") or []
    if not rules:
        return "none"
    parts: list[str] = []
    for rule in rules:
        kind = rule.get("kind", "constraint")
        raw = rule.get("raw_text") or rule.get("value")
        if raw is None:
            continue
        parts.append(f"{kind}: {raw}")
    return "; ".join(parts) if parts else "none"


def _latest_job_status(db: Session, trip_id: uuid.UUID) -> str | None:
    """Latest JobRun.status for a trip, or None if no row exists."""
    stmt = (
        select(JobRun.status)
        .where(JobRun.trip_id == trip_id)
        .order_by(JobRun.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _find_block_on_trip(db: Session, trip_id: uuid.UUID, block_id: uuid.UUID) -> Block | None:
    """SQL join: blocks → days → trips. Returns the Block row iff it
    belongs to a Day belonging to the given trip. Single round-trip.
    """
    stmt = (
        select(Block)
        .join(Day, Block.day_id == Day.id)
        .where(Block.id == block_id, Day.trip_id == trip_id)
    )
    return db.execute(stmt).scalar_one_or_none()


@router.post("/{trip_id}/blocks/{block_id}/alternative", status_code=status.HTTP_200_OK)
async def post_alternative(
    trip_id: uuid.UUID,
    block_id: uuid.UUID,
    _user: AuthedUser,
    db: SessionDep,
    payload: AlternativeRequest | None = None,
) -> Any:
    # Gate 2: trip exists.
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    # Gate 3: active job in flight.
    existing = await redis.get(f"trip:{trip_id}:active_job")
    if existing is not None:
        existing_id, existing_kind = decode_active_value(existing)  # type: ignore[misc]
        label = KIND_LABELS.get(existing_kind, "background")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": (
                    f"a {label} job is already in progress for trip {trip_id} "
                    f"(job {existing_id}); cancel via DELETE /trips/{trip_id}/plan "
                    "before retrying"
                ),
                "kind": "active_job",
                "active_job_id": existing_id,
                "active_job_kind": existing_kind,
            },
        )

    # Gate 4: trip in succeeded state. Latest JobRun.status determines
    # readiness; no row means never planned (the most common UX case
    # for a freshly created trip the user hasn't planned yet).
    latest_status = _latest_job_status(db, trip_id)
    if latest_status != "succeeded":
        state = "never_planned" if latest_status is None else latest_status
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "trip not ready for alternatives",
                "kind": "not_ready",
                "state": state,
            },
        )

    # Gate 5: block exists on THIS trip. Cross-trip lookups are 404,
    # not 403, so we don't leak the existence of a block on a different
    # trip. The defense against MCP host LLM UUID hallucination.
    block = _find_block_on_trip(db, trip_id, block_id)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="block not found on this trip",
        )

    # Gate 6: crew call with hard timeout.
    trip_state: dict[str, Any] = {
        "destination": trip.destination,
        "currency": trip.currency,
        "constraints_summary": _constraints_summary(trip.constraints),
    }
    block_payload: dict[str, Any] = {
        "type": block.type,
        "venue_name": block.venue_name,
        "duration_minutes": block.duration_minutes,
        "start_time": block.start_time,
    }
    reason = payload.reason if payload is not None else None

    try:
        result: dict[str, Any] = await asyncio.wait_for(
            asyncio.to_thread(
                find_alternative,
                trip_state=trip_state,
                block=block_payload,
                reason=reason,
            ),
            timeout=_FIND_ALTERNATIVE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        # Gate 7: timeout. NOTE on the leaked thread: Python cannot
        # cancel the running thread underneath asyncio.to_thread. The
        # CrewAI kickoff continues in the leaked thread until it
        # completes, burning ~$0.30 of LLM spend per incident. Tracked
        # for Phase 5 if validation shows >5% timeout rate. See commit
        # message for the full cost-transparency note.
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "detail": (
                    f"find_alternative timed out after "
                    f"{int(_FIND_ALTERNATIVE_TIMEOUT_SECONDS)} seconds"
                ),
                "kind": "timeout",
                "elapsed_seconds": _FIND_ALTERNATIVE_TIMEOUT_SECONDS,
                "trip_id": str(trip_id),
                "block_id": str(block_id),
            },
        )

    # Gate 8: success.
    return result
