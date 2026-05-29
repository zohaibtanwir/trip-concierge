"""GET /trips/{trip_id}/export?format=... — owner-side data download.

Slice 3.5 commit 2. Asymmetric auth with /shared:
- /shared is the public surface (intentionally unauth).
- /export is the OWNER-side data download — auth-protected.

Format is a query param constrained by Literal["json","markdown"];
FastAPI enforces the enum at the type layer, returning 422 for any
other value (e.g. ?format=pdf, deferred to ticket trip-concierge-de6).
Per slice-3.4a discipline discussion: single rare error path
doesn't justify a custom kind-structured-body; FastAPI's auto-422
is sufficient.

Content-Type matrix:
- json     → application/json
- markdown → text/markdown; charset=utf-8

The explicit charset=utf-8 on Markdown prevents browser-side
encoding ambiguity for non-ASCII destinations (₹ already; CJK
foreseeable).

No Content-Disposition: attachment header for v1.0a — MCP tool is
the primary consumer; browser-driven download is a Phase 4 concern
that can opt in via a future `?download=1` query param.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.db.session import get_session
from app.models.user import User
from app.schemas.trip import TripFullRead
from app.services import trip_export, trip_service

router = APIRouter(prefix="/trips", tags=["export"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


@router.get("/{trip_id}/export", response_class=Response)
def export_trip(
    trip_id: uuid.UUID,
    _user: AuthedUser,
    db: SessionDep,
    format: Literal["json", "markdown"] = "json",
) -> Response:
    trip = trip_service.get_trip_full(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    trip_read = TripFullRead.model_validate(trip)

    if format == "json":
        # FastAPI may auto-append ; charset=utf-8 — test allows that with .startswith.
        return Response(
            content=trip_export.render_json(trip_read),
            media_type="application/json",
        )
    # Markdown branch — explicit charset=utf-8 per slice 3.5 design.
    return PlainTextResponse(
        content=trip_export.render_markdown(trip_read),
        media_type="text/markdown; charset=utf-8",
    )
