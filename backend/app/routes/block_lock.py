"""PATCH /trips/{trip_id}/blocks/{block_id} — toggle Block.locked (slice 4.6 commit 1).

Per slice 4.6 Q5 sign-off: optimistic-UI lock toggle. Metadata-only
column write — no Redis state changes, no arq job enqueue. The
locked state is read by the regenerate_day worker at job dispatch
time per slice 3.3's hard contract.

Design call: NO 409 active-job guard. Lock toggle is cheap metadata
and doesn't conflict with crew work. Users can lock additional
blocks while a regenerate is in flight; the worker reads the
snapshot at dispatch time, so any toggle racing with an in-flight
regen is observed at the next dispatch.

Mirror of slice 4.5b's PATCH /trips/{id} pattern (column write +
Pydantic body + AuthedUser), scoped to Block:
- Pydantic body with single required field {locked: bool}
- Trip + block existence validation (404 — 404 not 403 to avoid
  leaking trip ownership; per slice 3.4a precedent in /alternative
  + /explain)
- 422 on missing/invalid body (Pydantic auto)
- Returns BlockRead with updated locked state

User-ownership beyond MCP token presence: deferred per ticket
`trip-concierge-wew` (P2, v1.0b security review). Inherits the
existing pattern across all current trip routes.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.db.session import get_session
from app.models.block import Block
from app.models.day import Day
from app.models.user import User
from app.schemas.day import BlockRead
from app.services import trip_service

router = APIRouter(prefix="/trips", tags=["block_lock"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


class BlockLockRequest(BaseModel):
    """PATCH /trips/{id}/blocks/{block_id} body."""

    model_config = ConfigDict(extra="forbid")

    locked: bool


def _find_block_on_trip(db: Session, trip_id: uuid.UUID, block_id: uuid.UUID) -> Block | None:
    """SQL join: blocks → days → trips. Returns the Block iff it
    belongs to a Day on the given trip. Single round-trip.

    Mirror of the same helper in routes/alternative.py + routes/explain.py
    — kept local rather than extracted to a shared module because the
    three call sites have slightly different downstream behavior and
    extraction would couple them. Worth revisiting if a fourth call
    site emerges.
    """
    stmt = (
        select(Block)
        .join(Day, Block.day_id == Day.id)
        .where(Block.id == block_id, Day.trip_id == trip_id)
    )
    return db.execute(stmt).scalar_one_or_none()


@router.patch(
    "/{trip_id}/blocks/{block_id}",
    response_model=BlockRead,
    status_code=status.HTTP_200_OK,
)
def update_block_lock(
    trip_id: uuid.UUID,
    block_id: uuid.UUID,
    payload: BlockLockRequest,
    _user: AuthedUser,
    db: SessionDep,
) -> BlockRead:
    # Gate 1: trip exists.
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    # Gate 2: block exists AND belongs to this trip.
    block = _find_block_on_trip(db, trip_id, block_id)
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found on trip")

    # Column write — no Redis touch, no enqueue.
    block.locked = payload.locked
    db.add(block)
    db.commit()
    db.refresh(block)

    return BlockRead.model_validate(block)
