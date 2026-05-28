"""POST /trips/{trip_id}/blocks/{block_id}/alternative — sync route tests.

Slice 3.4a commit 4. The route runs the find_alternative crew SYNCHRONOUSLY
inside the request (asyncio.wait_for + asyncio.to_thread, 90s timeout).
Unlike refine/regenerate which are async-via-arq, this one returns the
AlternativesList inline so the MCP tool can render alternatives in a
single Claude Desktop turn.

Six load-bearing tests:
1. Happy path 200 + crew INPUT contract (assert what we pass to crew —
   not just what we got back; this is the load-bearing pin per slice 3.4a
   file-tree session push-back).
2. 404 unknown trip — crew NOT called.
3. 409 trip not in succeeded state — body has kind="not_ready" + state;
   crew NOT called. Two sub-cases: never_planned and last-job-failed.
4. 404 block_id not on this trip's days — crew NOT called. This is the
   backend layer of the layered-defense against the MCP host LLM
   hallucinating a UUID-shaped block_id.
5. 504 + body kind="timeout" + elapsed_seconds + trip_id + block_id on
   crew timeout. Mock asyncio.wait_for to raise TimeoutError.
6. 401 no token.

Active-job 409 (the slice-3.3 reuse path) is exercised end-to-end here too
to confirm the kind="active_job" body shape stays distinguishable from the
kind="not_ready" body shape.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.trip import Trip
from app.models.user import User


def _make_trip_with_block(
    db: Session,
    user: User,
    *,
    constraints: dict[str, Any] | None = None,
    job_status: str | None = "succeeded",
) -> tuple[Trip, Block]:
    """Build a Trip with one Day, one Block, and (optionally) a terminal
    JobRun so the route's not-ready gate is satisfied.
    """
    trip = Trip(
        user_id=user.id,
        destination="Goa, India",
        currency="INR",
        group_size=2,
        pace="balanced",
        constraints=constraints if constraints is not None else {},
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    day = Day(trip_id=trip.id, day_number=1, summary="Day 1")
    db.add(day)
    db.commit()
    db.refresh(day)

    block = Block(
        day_id=day.id,
        order=2,
        type="meal",
        venue_name="Original Restaurant",
        start_time="19:00",
        duration_minutes=60,
        currency="INR",
    )
    db.add(block)
    db.commit()
    db.refresh(block)

    if job_status is not None:
        jr = JobRun(
            job_id=f"jr-{uuid.uuid4().hex[:8]}",
            trip_id=trip.id,
            kind="plan",
            status=job_status,
        )
        db.add(jr)
        db.commit()

    return trip, block


def _mock_pool(*, existing_active_job: bytes | None = None) -> AsyncMock:
    """Mirrors the constraints/regenerate test pattern. No enqueue here —
    this route does NOT enqueue (synchronous crew call), so we only mock
    .get for the active_job check.
    """
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    return pool


def _alternatives_dict() -> dict[str, Any]:
    """Stand-in for crew.find_alternative's return — AlternativesList.model_dump()."""
    return {
        "alternatives": [
            {
                "venue_name": f"Alt Venue {i}",
                "type": "meal",
                "duration_minutes": 60,
                "est_cost": 600.0,
                "currency": "INR",
                "source_urls": [f"https://example.com/alt{i}"],
                "rationale": f"Strong fit for vegetarian constraint and pace balanced i={i}",
            }
            for i in range(1, 4)
        ]
    }


def test_alternative_returns_200_and_pins_crew_input_contract(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path PLUS the load-bearing crew-input pin (push-back from
    file-tree session). Without these crew-input assertions the test
    passes even if the route hands garbage to crew.find_alternative.

    The pinned contract:
    - trip_state.destination from Trip.destination
    - trip_state.currency from Trip.currency
    - trip_state.constraints_summary from a join of Trip.constraints["rules"]
      values — NOT the raw JSONB blob
    - block.type / venue_name / duration_minutes / start_time from the
      looked-up Block row — NOT from the URL or request body
    - reason from the request body
    """
    client, user = authed_client
    trip, block = _make_trip_with_block(
        db_session,
        user,
        constraints={
            "rules": [
                {"kind": "dietary", "value": "vegetarian", "raw_text": "I'm vegetarian"},
                {"kind": "no_go", "value": "nightclubs", "raw_text": "no nightclubs"},
            ]
        },
    )

    pool = _mock_pool()
    captured: dict[str, Any] = {}

    def fake_find_alternative(
        *,
        trip_state: dict[str, Any],
        block: dict[str, Any],
        reason: str | None = None,
        step_callback: Any = None,
    ) -> dict[str, Any]:
        captured["trip_state"] = trip_state
        captured["block"] = block
        captured["reason"] = reason
        return _alternatives_dict()

    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", side_effect=fake_find_alternative),
    ):
        resp = client.post(
            f"/trips/{trip.id}/blocks/{block.id}/alternative",
            json={"reason": "restaurant closed for renovations"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    alts = body["alternatives"]
    assert len(alts) == 3
    for alt in alts:
        assert "venue_name" in alt
        assert "duration_minutes" in alt
        assert "source_urls" in alt and len(alt["source_urls"]) >= 1

    # Crew-input contract — load-bearing per file-tree push-back.
    assert captured["trip_state"]["destination"] == "Goa, India"
    assert captured["trip_state"]["currency"] == "INR"
    summary = captured["trip_state"]["constraints_summary"]
    assert "vegetarian" in summary
    assert "nightclubs" in summary

    assert captured["block"]["type"] == "meal"
    assert captured["block"]["venue_name"] == "Original Restaurant"
    assert captured["block"]["duration_minutes"] == 60
    assert captured["block"]["start_time"] == "19:00"

    assert captured["reason"] == "restaurant closed for renovations"


def test_alternative_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    pool = _mock_pool()
    mock_crew = MagicMock(return_value=_alternatives_dict())
    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", mock_crew),
    ):
        resp = client.post(
            f"/trips/{uuid.uuid4()}/blocks/{uuid.uuid4()}/alternative",
            json={"reason": "any"},
        )
    assert resp.status_code == 404
    assert not mock_crew.called, "crew must NOT be called on 404 trip"


def test_alternative_returns_409_when_trip_not_in_succeeded_state(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Two sub-cases for the not-ready path:
    1. No JobRun at all (state="never_planned")
    2. Latest JobRun.status="failed" (state="failed")

    Both must return 409 with body kind="not_ready" + state field. The
    `state` field is what the MCP tool will surface to the user via the
    commit-5 formatter.
    """
    client, user = authed_client
    mock_crew = MagicMock(return_value=_alternatives_dict())

    # Sub-case 1: never planned.
    trip1, block1 = _make_trip_with_block(db_session, user, job_status=None)
    pool = _mock_pool()
    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", mock_crew),
    ):
        r1 = client.post(
            f"/trips/{trip1.id}/blocks/{block1.id}/alternative",
            json={"reason": "x"},
        )
    assert r1.status_code == 409
    body1 = r1.json()
    assert body1["kind"] == "not_ready"
    assert body1["state"] == "never_planned"
    assert not mock_crew.called

    # Sub-case 2: latest JobRun failed.
    trip2, block2 = _make_trip_with_block(db_session, user, job_status="failed")
    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", mock_crew),
    ):
        r2 = client.post(
            f"/trips/{trip2.id}/blocks/{block2.id}/alternative",
            json={"reason": "x"},
        )
    assert r2.status_code == 409
    body2 = r2.json()
    assert body2["kind"] == "not_ready"
    assert body2["state"] == "failed"
    assert not mock_crew.called


def test_alternative_returns_404_for_unknown_block_id(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """The backend's layer of the UUID-hallucination defense. Schema +
    prompt prohibitions live in agents/; this is the route's belt.
    """
    client, user = authed_client
    trip, _real_block = _make_trip_with_block(db_session, user)
    pool = _mock_pool()
    mock_crew = MagicMock(return_value=_alternatives_dict())

    # Hallucinated block_id — well-formed UUID but not on this trip.
    fake_block_id = uuid.uuid4()
    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", mock_crew),
    ):
        resp = client.post(
            f"/trips/{trip.id}/blocks/{fake_block_id}/alternative",
            json={"reason": "any"},
        )
    assert resp.status_code == 404
    assert "block" in resp.json()["detail"].lower()
    assert not mock_crew.called, "crew must NOT be called on hallucinated block_id"


def test_alternative_returns_504_on_crew_timeout(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Mock asyncio.wait_for to raise TimeoutError. Assert 504 + structured
    body with kind="timeout" + elapsed_seconds + trip_id + block_id.

    NOTE: This test pins the body SHAPE. It does NOT exercise the actual
    asyncio.to_thread → CrewAI cancellation path — Python can't cancel
    running threads, so the cost-leak documented in the commit message is
    a real v1.0 limitation.
    """
    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user)
    pool = _mock_pool()

    async def fake_wait_for(_coro: Any, timeout: float) -> Any:  # noqa: ARG001
        # Close the coroutine so pytest's event loop doesn't warn about
        # never-awaited coroutines in the leaked-thread emulation.
        with contextlib.suppress(Exception):
            _coro.close()
        raise TimeoutError

    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.asyncio.wait_for", side_effect=fake_wait_for),
    ):
        resp = client.post(
            f"/trips/{trip.id}/blocks/{block.id}/alternative",
            json={"reason": "trying"},
        )
    assert resp.status_code == 504, resp.text
    body = resp.json()
    assert body["kind"] == "timeout"
    assert body["elapsed_seconds"] == 90.0
    assert body["trip_id"] == str(trip.id)
    assert body["block_id"] == str(block.id)


def test_alternative_returns_401_without_token(client: TestClient) -> None:
    resp = client.post(
        f"/trips/{uuid.uuid4()}/blocks/{uuid.uuid4()}/alternative",
        json={"reason": "anything"},
    )
    assert resp.status_code == 401


def test_active_job_409_body_shape_is_distinguishable_from_not_ready(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """When an active job is in flight, 409 body has kind="active_job"
    + active_job_id + active_job_kind. This MUST be parseable apart from
    the kind="not_ready" body so the MCP tool can branch correctly in
    commit 5.

    Uses the slice-3.3 encode_active_value JSON format.
    """
    import json as json_mod

    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user)
    existing = json_mod.dumps({"job_id": "refine-existing", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing)
    mock_crew = MagicMock(return_value=_alternatives_dict())

    with (
        patch("app.routes.alternative.create_pool", return_value=pool),
        patch("app.routes.alternative.find_alternative", mock_crew),
    ):
        resp = client.post(
            f"/trips/{trip.id}/blocks/{block.id}/alternative",
            json={"reason": "x"},
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["kind"] == "active_job"
    assert body["active_job_id"] == "refine-existing"
    assert body["active_job_kind"] == "refine"
    assert "refinement" in body["detail"], "must surface KIND_LABELS['refine']='refinement'"
    assert not mock_crew.called
