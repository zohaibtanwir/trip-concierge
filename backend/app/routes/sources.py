"""POST /trips/{trip_id}/sources — attach user-pasted research.

Slice 3.4b commit 3. Two paths in one route:

  1. {url: ...} → fetch via source_ingestion.ingest (6-defense
     stack from commit 2), persist UserSource with the extracted
     text.
  2. {text: ...} → passthrough storage, content_type="user_text".

Exactly one of {url, text} is required — both or neither yields 422
via the model_validator below.

Each of the four ingestion exception classes maps to a distinct
HTTP status code + structured body with `kind` field (slice-3.4a
discipline applied to a new failure-mode surface):

  DeniedHostError              → 400 + kind="denied_host"
  FetchFailedError             → 502 + kind="fetch_failed"
  UnsupportedContentTypeError  → 415 + kind="unsupported_content_type"
  ContentTooLargeError         → 413 + kind="too_large" + byte_count

Gate sequence (top to bottom, fail-fast):
  1. Auth (require_mcp_token; 401)
  2. Trip exists (404)
  3. Active job in flight (409 + kind="active_job") — slice-3.3 reuse
  4. Validation: exactly one of {url, text} (422 via Pydantic)
  5. Either: source_ingestion.ingest with typed-exception routing
       Or:    passthrough storage for the text path
  6. 200 + {source_id, content_type, char_count}
"""

from __future__ import annotations

import uuid
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.routes.plan import KIND_LABELS, decode_active_value
from app.services import source_ingestion, trip_service
from app.services.source_ingestion import (
    ContentTooLargeError,
    DeniedHostError,
    FetchFailedError,
    UnsupportedContentTypeError,
)

router = APIRouter(prefix="/trips", tags=["sources"])

SessionDep = Annotated[Session, Depends(get_session)]
AuthedUser = Annotated[User, Depends(require_mcp_token)]


class AddSourceRequest(BaseModel):
    """POST /trips/{id}/sources body. Exactly one of {url, text}."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(
        default=None,
        max_length=2000,
        description="URL to fetch via source_ingestion (6-defense stack).",
    )
    text: str | None = Field(
        default=None,
        max_length=200_000,
        description="Raw user-pasted text. ~200KB cap mirrors source_ingestion's 2MB byte cap.",
    )

    @model_validator(mode="after")
    def _exactly_one_payload(self) -> AddSourceRequest:
        if (self.url is None) == (self.text is None):
            raise ValueError("exactly one of `url` or `text` must be provided")
        return self


@router.post("/{trip_id}/sources", status_code=status.HTTP_200_OK, response_model=None)
async def post_source(
    trip_id: uuid.UUID,
    payload: AddSourceRequest,
    _user: AuthedUser,
    db: SessionDep,
) -> dict[str, object] | JSONResponse:
    trip = trip_service.get_trip(db, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trip not found")

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
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

    # Text passthrough path — no ingestion.
    if payload.text is not None:
        row = trip_service.append_user_source(
            db,
            trip_id=trip_id,
            url=None,
            raw_text=payload.text,
            content_type="user_text",
        )
        return {
            "source_id": str(row.id),
            "content_type": "user_text",
            "char_count": len(payload.text),
        }

    # URL fetch path — ingestion + typed-exception → status routing.
    assert payload.url is not None  # validator guarantees exactly one
    try:
        result = await source_ingestion.ingest(payload.url)
    except DeniedHostError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e), "kind": "denied_host"},
        )
    except FetchFailedError as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(e), "kind": "fetch_failed"},
        )
    except UnsupportedContentTypeError as e:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content={"detail": str(e), "kind": "unsupported_content_type"},
        )
    except ContentTooLargeError as e:
        # Starlette/FastAPI alias: HTTP_413_REQUEST_ENTITY_TOO_LARGE is
        # deprecated in favor of HTTP_413_CONTENT_TOO_LARGE per RFC 9110.
        # Use the literal 413 to stay portable across versions.
        return JSONResponse(
            status_code=413,
            content={"detail": str(e), "kind": "too_large", "byte_count": e.byte_count},
        )

    row = trip_service.append_user_source(
        db,
        trip_id=trip_id,
        url=payload.url,
        raw_text=result.raw_text,
        content_type=result.content_type,
    )
    return {
        "source_id": str(row.id),
        "content_type": result.content_type,
        "char_count": len(result.raw_text),
    }
