"""GET /shared/{trip_id} — INTENTIONALLY unauthenticated trip viewer.

Slice 3.5 commit 2. The unauth surface for the share_trip MCP tool.

Privacy model (v1.0a):
  Share-by-URL — anyone with the trip_id (UUIDv4, 128 bits of
  entropy) can view the trip. No sign-in, no per-link token, no
  revocation. Trip data carries no PII beyond destination + travel
  preferences; UUID guessability bounds the attack surface.

Why no `require_mcp_token` dependency: the share_trip MCP tool
generates `https://tripconcierge.app/shared/{trip_id}` URLs the
user shares with people who don't have a token. Auth would defeat
the entire share UX.

Revocable tokens (Trip.share_token column + rotation API + 410
Gone on revoked) are tracked as ticket trip-concierge-gid (P3,
v1.0b). Until that ships, /shared is intentionally token-less.

The route reuses TripFullRead — same schema as GET /trips/{id}/full.
Don't invent a parallel shape.

State-gate discipline: 200 is returned whenever the trip exists,
regardless of `Trip.status` or whether `Trip.days` is empty. The
state-aware "not ready to share" messaging lives at the MCP-tool
layer (slice 3.5 commit 3 — format_share_not_ready). A future
Phase 4 PWA can render its own "still planning" UI from the data
without the endpoint imposing a state model.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.trip import TripFullRead
from app.services import trip_service

router = APIRouter(prefix="/shared", tags=["shared"])

SessionDep = Annotated[Session, Depends(get_session)]


# Intentionally unauthenticated — anyone with the trip_id (128-bit UUIDv4
# entropy) can view. v1.0a privacy model is share-by-URL. See slice 3.5
# design + revocable-tokens ticket trip-concierge-gid for the v1.0b upgrade
# path. A future "let's add auth" change must also update
# test_shared_route_returns_200_without_any_auth_token_v1_0a_privacy_model.
@router.get("/{trip_id}", response_model=TripFullRead)
def get_shared_trip(trip_id: uuid.UUID, db: SessionDep) -> TripFullRead:
    trip = trip_service.get_trip_full(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")
    return TripFullRead.model_validate(trip)
