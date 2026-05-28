"""append_constraint: storage helper for Trip.constraints JSONB.

Slice 3.4a commit 1. Establishes the wrap pattern from the file-tree
session's Q1 — instead of replacing Trip.constraints, we ensure a
`rules` key exists (creates as list if absent), append the new
constraint dict, and leave any other keys in the JSONB alone.

Dedup compares (kind, value) only — raw_text and created_at vary
per call and must NOT defeat dedup. Without this, every retry of
"I'm vegetarian" would multiply rules.

Tests use the real db_session fixture (conftest seeds + truncates
per test). No mocks — JSONB round-trip behavior is part of what's
being verified.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User
from app.services.trip_service import append_constraint


def _make_trip(db: Session, *, constraints: dict | None = None) -> Trip:
    user = User(email=f"constr-{uuid.uuid4()}@test.com", name="Constraint Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
        constraints=constraints if constraints is not None else {},
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def test_first_constraint_creates_rules_list_and_appends(db_session: Session) -> None:
    """Trip starts with empty constraints={}; first append_constraint call
    creates the rules list and adds the constraint dict.
    """
    trip = _make_trip(db_session)
    assert "rules" not in trip.constraints

    append_constraint(
        db_session,
        trip_id=trip.id,
        kind="dietary",
        value="vegetarian",
        raw_text="I'm vegetarian",
    )
    db_session.refresh(trip)

    rules = trip.constraints["rules"]
    assert isinstance(rules, list)
    assert len(rules) == 1
    assert rules[0]["kind"] == "dietary"
    assert rules[0]["value"] == "vegetarian"
    assert rules[0]["raw_text"] == "I'm vegetarian"
    assert "created_at" in rules[0]


def test_second_constraint_different_kind_value_appends_preserving_order(
    db_session: Session,
) -> None:
    """Adding a second constraint with a different (kind, value) appends to
    the existing list. Order is insertion-order (first added is first).
    """
    trip = _make_trip(db_session)
    append_constraint(
        db_session, trip_id=trip.id, kind="dietary", value="vegetarian", raw_text="vegetarian"
    )
    append_constraint(
        db_session, trip_id=trip.id, kind="budget", value=3000, raw_text="₹3000/day cap"
    )
    db_session.refresh(trip)

    rules = trip.constraints["rules"]
    assert len(rules) == 2
    assert rules[0]["kind"] == "dietary"
    assert rules[1]["kind"] == "budget"
    assert rules[1]["value"] == 3000


def test_duplicate_constraint_by_kind_and_value_is_noop(db_session: Session) -> None:
    """Adding the same (kind, value) twice must NOT duplicate the rule.
    The raw_text from the FIRST call is preserved (no overwrite); dedup
    compares (kind, value) only, ignoring raw_text and created_at.
    """
    trip = _make_trip(db_session)
    append_constraint(
        db_session,
        trip_id=trip.id,
        kind="dietary",
        value="vegetarian",
        raw_text="I'm vegetarian",
    )
    append_constraint(
        db_session,
        trip_id=trip.id,
        kind="dietary",
        value="vegetarian",
        raw_text="just remembered, I'm vegetarian!!!",  # different raw_text
    )
    db_session.refresh(trip)

    rules = trip.constraints["rules"]
    assert len(rules) == 1, "duplicate (kind, value) must not append a second rule"
    # Original raw_text preserved — first wins.
    assert rules[0]["raw_text"] == "I'm vegetarian"


def test_three_constraints_accumulate_in_order(db_session: Session) -> None:
    """No implicit reset between calls — constraints from successive
    sessions accumulate. Final list has 3 entries in insertion order.
    """
    trip = _make_trip(db_session)
    append_constraint(
        db_session, trip_id=trip.id, kind="dietary", value="vegetarian", raw_text="veg"
    )
    append_constraint(
        db_session, trip_id=trip.id, kind="no_go", value="nightclubs", raw_text="no nightclubs"
    )
    append_constraint(
        db_session,
        trip_id=trip.id,
        kind="walking_limit",
        value=5,
        raw_text="no more than 5km/day",
    )
    db_session.refresh(trip)

    rules = trip.constraints["rules"]
    assert [r["kind"] for r in rules] == ["dietary", "no_go", "walking_limit"]
    assert [r["value"] for r in rules] == ["vegetarian", "nightclubs", 5]


def test_raises_value_error_on_unknown_trip(db_session: Session) -> None:
    """Defensive — if the trip_id doesn't exist, raise rather than
    silently creating orphan data. Worker shouldn't call us on a
    missing trip; failing loudly surfaces the invariant break.
    """
    with pytest.raises(ValueError, match="trip"):
        append_constraint(
            db_session,
            trip_id=uuid.uuid4(),
            kind="dietary",
            value="vegetarian",
            raw_text="veg",
        )


def test_first_constraint_preserves_other_jsonb_keys(db_session: Session) -> None:
    """The wrap pattern's whole correctness rests on "we add the rules
    key without disturbing anything else in the dict." This test pins
    that invariant against a Phase 4 surprise where the PWA stores
    other constraint metadata alongside.
    """
    trip = _make_trip(
        db_session,
        constraints={
            "some_other_key": "preserved",
            "phase4_metadata": {"nested": True, "count": 42},
        },
    )

    append_constraint(
        db_session,
        trip_id=trip.id,
        kind="dietary",
        value="vegetarian",
        raw_text="vegetarian",
    )
    db_session.refresh(trip)

    # Wrap preserved the pre-existing keys verbatim.
    assert trip.constraints["some_other_key"] == "preserved"
    assert trip.constraints["phase4_metadata"] == {"nested": True, "count": 42}
    # AND the rules list was added with one entry.
    rules = trip.constraints["rules"]
    assert isinstance(rules, list) and len(rules) == 1
    assert rules[0]["kind"] == "dietary"
