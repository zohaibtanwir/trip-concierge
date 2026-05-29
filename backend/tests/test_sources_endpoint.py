"""POST /trips/{trip_id}/sources — route + 6-defense exception routing.

Slice 3.4b commit 3. The route accepts EITHER a `url` (fetched via
source_ingestion.ingest) OR `text` (passthrough). Each of the four
ingestion exception classes maps to a distinct HTTP status code +
structured body (kind field discipline from slice 3.4a):

  DeniedHostError              → 400 + kind="denied_host"
  FetchFailedError             → 502 + kind="fetch_failed"
  UnsupportedContentTypeError  → 415 + kind="unsupported_content_type"
  ContentTooLargeError         → 413 + kind="too_large" + byte_count

Five load-bearing cases:
1. Happy path URL post — ingest succeeds, UserSource persisted, body
   shape {source_id, content_type, char_count}.
2. Plain text post — no ingest call, UserSource persisted with
   url=None and content_type="user_text".
3. Parametrized 4 exceptions — one focused test per status/kind shape.
4. 404 trip not found / 409 active job in flight — gate sequence.
5. 401 no token / 422 neither / 422 both — auth + validation.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User
from app.models.user_source import UserSource
from app.services.source_ingestion import (
    ContentTooLargeError,
    DeniedHostError,
    FetchFailedError,
    IngestResult,
    UnsupportedContentTypeError,
)


def _make_trip(db: Session, user: User) -> Trip:
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def _mock_pool(*, existing_active_job: bytes | None = None) -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    return pool


def _user_sources_for(db: Session, trip_id: uuid.UUID) -> list[UserSource]:
    return list(db.execute(select(UserSource).where(UserSource.trip_id == trip_id)).scalars())


async def test_sources_happy_path_url_post_persists_user_source(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Ingest returns a canned IngestResult; route persists UserSource
    and surfaces the trio (source_id, content_type, char_count) the
    MCP formatter consumes.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()

    fake_result = IngestResult(
        raw_text="Goa locals recommend Vinayak Family Restaurant.",
        content_type="url_fetched/html",
        byte_count=1234,
    )
    fake_ingest = AsyncMock(return_value=fake_result)

    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        resp = client.post(
            f"/trips/{trip.id}/sources",
            json={"url": "https://example.com/goa-tips"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "source_id" in body
    assert body["content_type"] == "url_fetched/html"
    assert body["char_count"] == len(fake_result.raw_text)

    # UserSource row persisted with the ingested text and the original URL.
    rows = _user_sources_for(db_session, trip.id)
    assert len(rows) == 1
    assert rows[0].url == "https://example.com/goa-tips"
    assert "Vinayak" in rows[0].raw_text
    assert rows[0].content_type == "url_fetched/html"


async def test_sources_plain_text_post_skips_ingestion_and_passes_through(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """No URL → no ingest call. UserSource row has url=None,
    content_type="user_text", and the raw_text echoed verbatim.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()
    fake_ingest = AsyncMock()

    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        resp = client.post(
            f"/trips/{trip.id}/sources",
            json={"text": "my friend texted me: try Vinayak in North Goa"},
        )

    assert resp.status_code == 200, resp.text
    assert not fake_ingest.called, "text path must NOT call source_ingestion.ingest"

    body = resp.json()
    assert body["content_type"] == "user_text"
    assert body["char_count"] == len("my friend texted me: try Vinayak in North Goa")

    rows = _user_sources_for(db_session, trip.id)
    assert len(rows) == 1
    assert rows[0].url is None
    assert rows[0].content_type == "user_text"
    assert rows[0].raw_text == "my friend texted me: try Vinayak in North Goa"


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_kind", "extra_check"),
    [
        (
            DeniedHostError("denied host: localhost"),
            400,
            "denied_host",
            None,
        ),
        (
            FetchFailedError("timeout fetching https://example.com"),
            502,
            "fetch_failed",
            None,
        ),
        (
            UnsupportedContentTypeError(
                "unsupported Content-Type 'image/png' for https://example.com/x.png"
            ),
            415,
            "unsupported_content_type",
            None,
        ),
        (
            ContentTooLargeError(url="https://example.com/huge", byte_count=3_500_000),
            413,
            "too_large",
            ("byte_count", 3_500_000),
        ),
    ],
)
async def test_sources_routes_each_ingestion_exception_to_distinct_status_and_kind(
    authed_client: tuple[TestClient, User],
    db_session: Session,
    exception: Exception,
    expected_status: int,
    expected_kind: str,
    extra_check: tuple[str, Any] | None,
) -> None:
    """The corpus-shape pin. Each defense class surfaces a distinct
    (status, kind) pair. A future refactor that collapses two of these
    into one shape fails exactly the parametrize case for that pair —
    diagnostics name the regression precisely.
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()
    fake_ingest = AsyncMock(side_effect=exception)

    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        resp = client.post(
            f"/trips/{trip.id}/sources",
            json={"url": "https://example.com/whatever"},
        )

    assert resp.status_code == expected_status, resp.text
    body = resp.json()
    assert body["kind"] == expected_kind
    assert "detail" in body and isinstance(body["detail"], str)

    if extra_check is not None:
        key, value = extra_check
        assert body[key] == value

    # No UserSource row persisted on any failure path.
    assert _user_sources_for(db_session, trip.id) == []


async def test_sources_returns_404_for_unknown_trip_and_409_for_active_job(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Two gate-sequence sub-cases:
    - Unknown trip_id → 404 + "trip not found", ingest NOT called.
    - Known trip + active refine job → 409 + kind="active_job" +
      slice-3.3 KIND_LABELS label, ingest NOT called.
    """
    client, user = authed_client
    fake_ingest = AsyncMock()

    # Sub-case A: unknown trip.
    pool = _mock_pool()
    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        r404 = client.post(
            f"/trips/{uuid.uuid4()}/sources",
            json={"url": "https://example.com"},
        )
    assert r404.status_code == 404
    assert not fake_ingest.called

    # Sub-case B: known trip + active refine job.
    trip = _make_trip(db_session, user)
    existing = json.dumps({"job_id": "refine-existing", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing)
    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        r409 = client.post(
            f"/trips/{trip.id}/sources",
            json={"url": "https://example.com"},
        )
    assert r409.status_code == 409, r409.text
    body = r409.json()
    assert body["kind"] == "active_job"
    assert body["active_job_id"] == "refine-existing"
    assert body["active_job_kind"] == "refine"
    assert "refinement" in body["detail"]
    assert not fake_ingest.called


def test_sources_returns_401_without_token(client: TestClient) -> None:
    """Auth gate — must take only the unauthenticated `client` fixture.
    The authed_client fixture mutates the shared TestClient's headers,
    so taking both fixtures in one test would inadvertently authenticate
    the 'unauthenticated' sub-case. Slice 3.4a precedent.
    """
    resp = client.post(
        f"/trips/{uuid.uuid4()}/sources",
        json={"url": "https://example.com"},
    )
    assert resp.status_code == 401


async def test_sources_returns_422_when_payload_has_neither_or_both_of_url_text(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Pydantic exactly-one invariant (model_validator). Two sub-cases:
    - {} → 422 (neither)
    - {url, text} → 422 (both)
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()
    fake_ingest = AsyncMock()

    with (
        patch("app.routes.sources.create_pool", return_value=pool),
        patch("app.routes.sources.source_ingestion.ingest", fake_ingest),
    ):
        r_neither = client.post(f"/trips/{trip.id}/sources", json={})
        r_both = client.post(
            f"/trips/{trip.id}/sources",
            json={"url": "https://example.com", "text": "hi"},
        )

    assert r_neither.status_code == 422
    assert r_both.status_code == 422
    assert not fake_ingest.called
    assert _user_sources_for(db_session, trip.id) == []
