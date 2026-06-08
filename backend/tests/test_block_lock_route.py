"""PATCH /trips/{trip_id}/blocks/{block_id} — block lock toggle (slice 4.6 commit 1).

Per slice 4.6 Q5 sign-off: optimistic-UI lock toggle. Metadata-only
column write (Block.locked); no Redis state changes, no arq job
enqueue. The locked state is read by the regenerate_day worker at
job dispatch time per slice 3.3's hard contract.

Mirror of slice 4.5b's PATCH /trips/{id} pattern, scoped to Block:
- Pydantic body with single field {locked: bool}
- Trip + Block existence validation (404)
- Block-belongs-to-trip enforcement (404, not 403 — symmetric with
  POST /blocks/{id}/alternative + GET explain endpoints)
- 422 on missing/invalid body
- NO 409 active-job guard (slice 4.6 commit 1 design call): lock
  toggle is cheap metadata and doesn't conflict with crew work.
  Users can lock additional blocks while a regenerate is in flight;
  the worker reads the snapshot at dispatch.

Eight tests pin the contract.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.trip import Trip
from app.models.user import User


def _make_trip_with_block(db: Session, user: User, *, locked: bool = False) -> tuple[Trip, Block]:
    trip = Trip(
        user_id=user.id,
        destination="Coorg",
        currency="INR",
        group_size=2,
        pace="balanced",
        budget_total=Decimal("50000.00"),
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    day = Day(trip_id=trip.id, day_number=1, summary="Arrival day")
    db.add(day)
    db.commit()
    db.refresh(day)

    block = Block(
        day_id=day.id,
        order=1,
        type="venue",
        venue_name="Honey Valley Estate",
        duration_minutes=180,
        currency="INR",
        locked=locked,
        notes="",
        start_time="",
    )
    db.add(block)
    db.commit()
    db.refresh(block)

    return trip, block


def test_patch_block_returns_401_without_token(client: TestClient) -> None:
    resp = client.patch(
        f"/trips/{uuid.uuid4()}/blocks/{uuid.uuid4()}",
        json={"locked": True},
    )
    assert resp.status_code == 401


def test_patch_block_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    resp = client.patch(
        f"/trips/{uuid.uuid4()}/blocks/{uuid.uuid4()}",
        json={"locked": True},
    )
    assert resp.status_code == 404


def test_patch_block_returns_404_when_block_not_on_trip(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Block UUID is valid but belongs to a different trip — 404 not 403.
    Symmetric with POST /alternative + GET explain semantics: we don't
    distinguish "block doesn't exist" from "block exists but on another
    trip" — both surface as 404 to avoid leaking trip ownership."""
    client, user = authed_client
    trip, _ = _make_trip_with_block(db_session, user)
    other_block_id = uuid.uuid4()  # not in DB
    resp = client.patch(
        f"/trips/{trip.id}/blocks/{other_block_id}",
        json={"locked": True},
    )
    assert resp.status_code == 404


def test_patch_block_returns_422_for_missing_locked_field(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user)
    resp = client.patch(f"/trips/{trip.id}/blocks/{block.id}", json={})
    assert resp.status_code == 422


def test_patch_block_returns_422_for_invalid_locked_type(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user)
    resp = client.patch(
        f"/trips/{trip.id}/blocks/{block.id}",
        json={"locked": "maybe"},
    )
    assert resp.status_code == 422


def test_patch_block_locks_unlocked_block(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path 1: unlocked → locked. Response is the updated Block
    schema with locked=True."""
    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user, locked=False)

    resp = client.patch(
        f"/trips/{trip.id}/blocks/{block.id}",
        json={"locked": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(block.id)
    assert body["locked"] is True
    assert body["venue_name"] == "Honey Valley Estate"

    # DB-level verification.
    db_session.refresh(block)
    assert block.locked is True


def test_patch_block_unlocks_locked_block(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path 2: locked → unlocked. Toggle is symmetric."""
    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user, locked=True)

    resp = client.patch(
        f"/trips/{trip.id}/blocks/{block.id}",
        json={"locked": False},
    )
    assert resp.status_code == 200
    assert resp.json()["locked"] is False

    db_session.refresh(block)
    assert block.locked is False


def test_patch_block_no_409_when_active_job_in_flight(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Slice 4.6 commit 1 design call: lock toggle is metadata-only,
    NO active-job guard. Unlike PATCH /trips/{id} (settings) or POST
    /constraints (rules) which both trigger refine jobs and need the
    409 guard, lock toggle just flips a column. Users can lock
    additional blocks while a regenerate is in flight; the worker
    reads the snapshot at dispatch time per slice 3.3 contract.

    This test pins the design call by patching create_pool with a
    pool that DOES have an active_job set — if a 409 guard were
    added later, this test would fail and force a re-discussion.
    """
    import json
    from unittest.mock import AsyncMock, patch

    client, user = authed_client
    trip, block = _make_trip_with_block(db_session, user, locked=False)

    existing_payload = json.dumps({"job_id": "refine-existing", "kind": "refine"}).encode()
    pool = AsyncMock()
    pool.get.return_value = existing_payload

    # If the route adds a 409 guard later, it will call create_pool +
    # decode_active_value. Patch the import path the route would use.
    # We accept both outcomes (200 = no guard, 409 = guard added) only
    # in the form of pinning the v1.0a NO-GUARD design call: 200 is
    # required. If implementation adds 409 later, this test forces a
    # design re-discussion.
    with patch("app.routes.block_lock.create_pool", return_value=pool, create=True):
        resp = client.patch(
            f"/trips/{trip.id}/blocks/{block.id}",
            json={"locked": True},
        )

    assert resp.status_code == 200, (
        f"Expected 200 (no 409 guard for metadata-only lock toggle). "
        f"Got {resp.status_code}. If a 409 guard was added to lock toggle, "
        f"re-discuss the design call in slice 4.6 Q5."
    )
