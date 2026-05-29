"""GET /trips/{trip_id}/explain/{block_id} — why-this-block read.

Slice 3.4b commit 3. Pure DB read backing the explain_recommendation
MCP tool. No LLM call, no outbound work, no writes.

Body shape (always 200 on resource-resolution success):

  {
    "block_id": "<uuid>",
    "venue_name": "...",
    "block_type": "venue" | "meal" | "activity" | "transit" | "rest",
    "rationale": <str | null>,
    "sources": [
      {"url": ..., "excerpt": ..., "confidence_score": <float | null>}, ...
    ],
    "user_source_matches": [
      {"user_source_id": "<uuid>", "url": ...}, ...
    ]
  }

**Gap-surfacing contract (slice-opening Q3):**
When JobRun.agent_summary lacks a rationale for this block — either
because no JobRun exists, or because the summary's entries don't
match this block — the body field `rationale` is `null` (JSON null),
NOT an empty string and NOT a placeholder message. The MCP tool
branches on `is None` to render the gap-text formatter. Honest
broken beats invisibly empty.

Block-lookup uses the same SQL join shape as routes/alternative.py
(`blocks → days → trips`). Cross-trip lookups return 404 — same
404 detail-string-parse trade-off, tracked in ticket trip-concierge-or8
for conversion to kind="block_not_found" / "trip_not_found".

The JobRun.agent_summary search is forgiving by design: matches
by block_id first, then falls back to venue_name. step_callback
(ticket qek) doesn't always capture block_id; venue_name match
is the fallback that lets v1.0a surface rationales the moment qek
is fixed without a route refactor.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.db.session import get_session
from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.user import User
from app.models.user_source import UserSource
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["explain"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


def _find_block_on_trip(db: Session, trip_id: uuid.UUID, block_id: uuid.UUID) -> Block | None:
    """SQL join blocks → days → trips. Duplicates routes/alternative.py's
    helper; deferred-abstraction discipline — lift to a service helper
    when a third call site appears.
    """
    stmt = (
        select(Block)
        .join(Day, Block.day_id == Day.id)
        .where(Block.id == block_id, Day.trip_id == trip_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def _latest_job_run(db: Session, trip_id: uuid.UUID) -> JobRun | None:
    stmt = (
        select(JobRun).where(JobRun.trip_id == trip_id).order_by(JobRun.created_at.desc()).limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _rationale_for_block(
    job_run: JobRun | None,
    block_id: uuid.UUID,
    venue_name: str,
) -> str | None:
    """Returns the rationale string from JobRun.agent_summary if present
    and non-empty for this block. Returns None on gap.

    Match priority: block_id → venue_name → None. Venue-name fallback
    handles qek-state agent_summary entries that captured the rationale
    but not the block_id.
    """
    if job_run is None or not job_run.agent_summary:
        return None
    for entry in job_run.agent_summary:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("block_id")) == str(block_id):
            r = entry.get("rationale")
            if isinstance(r, str) and r.strip():
                return r
    # Fall back to venue_name match.
    for entry in job_run.agent_summary:
        if not isinstance(entry, dict):
            continue
        if entry.get("venue_name") == venue_name:
            r = entry.get("rationale")
            if isinstance(r, str) and r.strip():
                return r
    return None


@router.get("/{trip_id}/explain/{block_id}", status_code=status.HTTP_200_OK)
async def get_explain(
    trip_id: uuid.UUID,
    block_id: uuid.UUID,
    _user: AuthedUser,
    db: SessionDep,
) -> dict[str, Any]:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    block = _find_block_on_trip(db, trip_id, block_id)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="block not found on this trip",
        )

    sources = list(db.execute(select(Source).where(Source.block_id == block_id)).scalars())

    # URL-overlap detection between Block.Sources and Trip.UserSources.
    # Build a {url: user_source_id} map for the trip's UserSources, then
    # intersect against the block's Source URLs. Two queries total.
    user_source_rows = db.execute(
        select(UserSource.id, UserSource.url).where(
            UserSource.trip_id == trip_id,
            UserSource.url.isnot(None),
        )
    ).all()
    user_source_url_to_id: dict[str, uuid.UUID] = {
        row.url: row.id for row in user_source_rows if row.url is not None
    }
    user_source_matches: list[dict[str, str]] = []
    for s in sources:
        if s.url in user_source_url_to_id:
            user_source_matches.append(
                {
                    "user_source_id": str(user_source_url_to_id[s.url]),
                    "url": s.url,
                }
            )

    rationale = _rationale_for_block(
        _latest_job_run(db, trip_id),
        block_id,
        block.venue_name,
    )

    return {
        "block_id": str(block_id),
        "venue_name": block.venue_name,
        "block_type": block.type,
        "rationale": rationale,
        "sources": [
            {
                "url": s.url,
                "excerpt": s.excerpt,
                "confidence_score": (
                    float(s.confidence_score) if s.confidence_score is not None else None
                ),
            }
            for s in sources
        ],
        "user_source_matches": user_source_matches,
    }
