"""POST /trips/{trip_id}/constraints — enqueue path tests.

Slice 3.4a commit 2. The route:
1. Appends the new constraint to Trip.constraints["rules"] via the
   commit-1 storage helper.
2. Synthesizes a refinement_description (per-kind framing + merge
   semantics).
3. Enqueues the existing `refine_trip` arq task (slice 3.3 commit 3).
4. Writes the active_job JSON with kind="refine" — add_constraint
   reuses the refine machinery; no new JobKind.

The 7 tests pin: auth gate, 404, 422, 202 happy path, 409 with the
slice-3.3 kind-aware label reuse, and the synthesizer's determinism
+ merge-semantics language.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User
from app.services.constraint_synthesizer import synthesize_constraint_refinement


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


def _mock_pool(
    *, existing_active_job: bytes | None = None, job_id: str = "constraint-job-1"
) -> AsyncMock:
    pool = AsyncMock()
    pool.get.return_value = existing_active_job
    job = MagicMock()
    job.job_id = job_id
    pool.enqueue_job.return_value = job
    pool.setex.return_value = True
    return pool


def test_constraints_returns_401_without_token(client: TestClient) -> None:
    resp = client.post(
        f"/trips/{uuid.uuid4()}/constraints",
        json={"constraint_text": "I'm vegetarian", "constraint_kind": "dietary"},
    )
    assert resp.status_code == 401


def test_constraints_returns_404_for_unknown_trip(
    authed_client: tuple[TestClient, User],
) -> None:
    client, _ = authed_client
    pool = _mock_pool()
    with patch("app.routes.constraints.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{uuid.uuid4()}/constraints",
            json={"constraint_text": "I'm vegetarian", "constraint_kind": "dietary"},
        )
    assert resp.status_code == 404
    assert not pool.enqueue_job.called


def test_constraints_returns_422_for_missing_or_invalid_fields(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()

    with patch("app.routes.constraints.create_pool", return_value=pool):
        # Missing constraint_text.
        r1 = client.post(
            f"/trips/{trip.id}/constraints",
            json={"constraint_kind": "dietary"},
        )
        assert r1.status_code == 422

        # constraint_kind outside the Literal.
        r2 = client.post(
            f"/trips/{trip.id}/constraints",
            json={"constraint_text": "I'm vegetarian", "constraint_kind": "garbage"},
        )
        assert r2.status_code == 422

    assert not pool.enqueue_job.called, "no enqueue should happen on 422"


def test_constraints_returns_202_persists_and_enqueues_refine(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Happy path. Three load-bearing assertions:
    1. Trip.constraints["rules"] has the new entry persisted.
    2. arq enqueue called the EXISTING refine_trip task with the
       synthesized refinement_description as args[2].
    3. active_job Redis key written as JSON with kind="refine"
       (NOT a new "constraint" kind — see slice 3.4a Q3 design).
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool(job_id="constraint-job-x")

    with patch("app.routes.constraints.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/constraints",
            json={"constraint_text": "I'm vegetarian", "constraint_kind": "dietary"},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "constraint-job-x"
    assert body["status_url"] == f"/trips/{trip.id}/plan/status"

    # arq task name is "refine_trip" — reuses the refine worker.
    enqueue_args = pool.enqueue_job.call_args
    assert enqueue_args.args[0] == "refine_trip"
    assert enqueue_args.args[1] == str(trip.id)
    # The synthesized refinement_description is args[2] — verify the
    # per-kind framing + raw text both reach the worker.
    synthesized = enqueue_args.args[2]
    assert "constraint" in synthesized.lower()
    assert "vegetarian" in synthesized
    assert "dietary" in synthesized.lower()

    # active_job key written as JSON with kind="refine" — the underlying
    # job IS a refine; add_constraint is a UX abstraction.
    setex_args = pool.setex.call_args
    assert setex_args.args[0] == f"trip:{trip.id}:active_job"
    assert setex_args.args[1] == 900  # TTL unchanged
    payload = json.loads(setex_args.args[2])
    assert payload == {"job_id": "constraint-job-x", "kind": "refine"}

    # Trip.constraints["rules"] now has the new entry.
    db_session.refresh(trip)
    rules = trip.constraints["rules"]
    assert len(rules) == 1
    assert rules[0]["kind"] == "dietary"
    assert rules[0]["value"] == "I'm vegetarian"
    assert rules[0]["raw_text"] == "I'm vegetarian"


def test_constraints_returns_409_when_job_in_flight_with_kind_label(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """The 409 path. Verifies the slice-3.3 import-from-plan reuse: a
    refine job in flight produces a 409 with the "refinement" label
    in the detail message (from KIND_LABELS["refine"]).
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    existing_payload = json.dumps({"job_id": "refine-existing", "kind": "refine"}).encode()
    pool = _mock_pool(existing_active_job=existing_payload)

    with patch("app.routes.constraints.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/constraints",
            json={"constraint_text": "I'm vegetarian", "constraint_kind": "dietary"},
        )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "refinement" in detail, "must surface KIND_LABELS['refine']='refinement' label"
    assert "refine-existing" in detail
    assert not pool.enqueue_job.called

    # Trip.constraints["rules"] should NOT have been written on 409 —
    # we don't persist a constraint that can't be applied because
    # something else is in flight.
    db_session.refresh(trip)
    assert "rules" not in trip.constraints or trip.constraints["rules"] == []


def test_constraints_accepts_accessibility_kind(
    authed_client: tuple[TestClient, User],
    db_session: Session,
) -> None:
    """Slice 4.5 — `accessibility` kind added to the ConstraintKind Literal.

    PRD §F4 lists accessibility flag as one of the constraint controls.
    Slice 4.5's web constraint-panel surface ships a dedicated
    accessibility toggle; the backend route must accept the
    corresponding kind so the panel doesn't have to fall back to
    "custom" with descriptive text (which would muddle the per-kind
    framing in constraint_synthesizer).
    """
    client, user = authed_client
    trip = _make_trip(db_session, user)
    pool = _mock_pool()

    with patch("app.routes.constraints.create_pool", return_value=pool):
        resp = client.post(
            f"/trips/{trip.id}/constraints",
            json={
                "constraint_text": "Wheelchair-accessible venues only",
                "constraint_kind": "accessibility",
            },
        )

    assert resp.status_code == 202, response_text(resp)
    assert pool.enqueue_job.called, "accessibility constraint must enqueue refine"

    db_session.refresh(trip)
    rules = trip.constraints.get("rules", [])
    assert len(rules) == 1
    assert rules[0]["kind"] == "accessibility"


def response_text(resp) -> str:
    """Helper used only by the test above — flatten Pydantic 422 detail."""
    try:
        return resp.json()
    except Exception:
        return resp.text


def test_synthesizer_is_deterministic_across_repeat_calls() -> None:
    """Same (kind, value, raw_text) triplet → byte-identical output.
    Pins out timestamps, random IDs, dict-order nondeterminism. Critical
    for reproducible debugging: a constraint replayed via SQL replay
    must regenerate the same prompt the crew saw originally.
    """
    a = synthesize_constraint_refinement(
        kind="dietary", value="vegetarian", raw_text="I'm vegetarian"
    )
    b = synthesize_constraint_refinement(
        kind="dietary", value="vegetarian", raw_text="I'm vegetarian"
    )
    assert a == b
    # And a different (kind, value, raw_text) → different output.
    c = synthesize_constraint_refinement(kind="budget", value=3000, raw_text="₹3000/day cap")
    assert c != a


def test_synthesizer_carries_merge_semantics_language() -> None:
    """Pins push-back 4 from the file-tree session: the synthesized text
    must tell the crew the new constraint is IN ADDITION to existing
    constraints, do NOT relax prior ones, and the Auditor must verify
    the union holds. Without this language, the hierarchical manager_llm
    might drift on whether the new constraint REPLACES prior ones.

    This test catches a future refactor that accidentally strips the
    anti-replacement language.
    """
    text = synthesize_constraint_refinement(
        kind="dietary", value="vegetarian", raw_text="I'm vegetarian"
    )
    assert "IN ADDITION" in text, "anti-replacement language missing"
    assert "do not relax" in text.lower(), "prior-constraint protection missing"
    assert "ALL constraints" in text, "auditor-union language missing"
