"""_serialize_trip_for_crew extracts per_day_budget + max_walking_km
from constraints.rules[] — slice 4.5b commit 1.

Per Q3=A sign-off: extraction at the backend boundary, crew stays a
pure consumer of structured fields. The serializer becomes the single
source of truth for "what does the crew see" — Phase 5 review point.

Today (pre-4.5b), the serializer only flattens column-shaped fields
(destination, currency, budget_total, pace, group_size, days[]). It
does NOT scan constraints.rules[] for per_day_budget or
max_walking_km — so the auditor task template variables fall through
to DEFAULT_INPUTS' "unspecified" defaults, and the auditor fires
blind on three of four §F4 enforcement axes (per the slice 4.5b
load-bearing gap).

This test pins the post-4.5b behavior:
- A trip with a `budget` constraint rule (per-day budget cap, per
  synthesizer's existing semantic) → serialized dict has
  `per_day_budget` set to the rule's value.
- A trip with a `walking_limit` rule → serialized dict has
  `max_walking_km` set.
- A trip without those rules → fields are absent or None (worker
  passes "unspecified" through DEFAULT_INPUTS, unchanged behavior).
- Multiple rules of the same kind: most recent wins (rules are
  append-only; the latest reflects user's current intent).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User
from app.worker import _serialize_trip_for_crew


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(email=f"slice-4.5b-{uuid.uuid4()}@test.com", name="4.5b Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_trip(db: Session, user: User, *, constraints: dict | None = None) -> Trip:
    trip = Trip(
        user_id=user.id,
        destination="Coorg",
        currency="INR",
        group_size=2,
        pace="balanced",
        budget_total=Decimal("30000.00"),
        constraints=constraints or {},
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def _rule(kind: str, value: str) -> dict:
    return {
        "kind": kind,
        "value": value,
        "raw_text": value,
        "created_at": datetime.now(UTC).isoformat(),
    }


def test_serializer_extracts_per_day_budget_from_rules(
    db_session: Session,
    test_user: User,
) -> None:
    """`budget` kind = per-day cap per synthesizer's existing semantic
    (`Apply a new per-day budget cap of {value}`). The serializer must
    surface this into the crew-visible dict as `per_day_budget`."""
    trip = _make_trip(
        db_session,
        test_user,
        constraints={"rules": [_rule("budget", "5000")]},
    )
    serialized = _serialize_trip_for_crew(trip)
    assert serialized.get("per_day_budget") == "5000", (
        "Expected per_day_budget flattened from constraints.rules budget kind"
    )


def test_serializer_extracts_max_walking_km_from_rules(
    db_session: Session,
    test_user: User,
) -> None:
    trip = _make_trip(
        db_session,
        test_user,
        constraints={"rules": [_rule("walking_limit", "5")]},
    )
    serialized = _serialize_trip_for_crew(trip)
    assert serialized.get("max_walking_km") == "5", (
        "Expected max_walking_km flattened from constraints.rules walking_limit kind"
    )


def test_serializer_absent_when_no_rules(
    db_session: Session,
    test_user: User,
) -> None:
    """No rules → the new fields are absent OR None. Worker's downstream
    passes them to crew via TripRunRequest which defaults them to None,
    then DEFAULT_INPUTS substitutes 'unspecified'. Either shape is
    acceptable as long as it doesn't crash."""
    trip = _make_trip(db_session, test_user, constraints={})
    serialized = _serialize_trip_for_crew(trip)
    assert serialized.get("per_day_budget") in (None, ""), (
        "Expected per_day_budget absent/None for trip with no rules"
    )
    assert serialized.get("max_walking_km") in (None, ""), (
        "Expected max_walking_km absent/None for trip with no rules"
    )


def test_serializer_uses_most_recent_rule_when_duplicates(
    db_session: Session,
    test_user: User,
) -> None:
    """Constraints.rules is append-only. If the user submits a budget cap
    twice (e.g., '3000' then later '5000'), the later value reflects
    current intent — most recent wins.

    Note: append_constraint dedups on (kind, value), so this scenario
    requires DIFFERENT values for the same kind. The 5000 entry comes
    AFTER 3000 in the array; serializer takes the last."""
    trip = _make_trip(
        db_session,
        test_user,
        constraints={
            "rules": [
                _rule("budget", "3000"),
                _rule("budget", "5000"),  # later, different value
            ]
        },
    )
    serialized = _serialize_trip_for_crew(trip)
    assert serialized.get("per_day_budget") == "5000"


def test_serializer_unchanged_for_unrelated_kinds(
    db_session: Session,
    test_user: User,
) -> None:
    """Dietary/mobility/accessibility/no_go rules do NOT populate
    per_day_budget or max_walking_km — they go through their existing
    paths (synthesizer framing on POST /constraints, not via flattening).
    Verify the new flattening logic isn't a footgun for unrelated kinds."""
    trip = _make_trip(
        db_session,
        test_user,
        constraints={
            "rules": [
                _rule("dietary", "vegetarian"),
                _rule("mobility", "no-stairs"),
                _rule("accessibility", "wheelchair"),
                _rule("no_go", "loud bars"),
            ]
        },
    )
    serialized = _serialize_trip_for_crew(trip)
    # No budget rule → per_day_budget should not be set.
    assert serialized.get("per_day_budget") in (None, "")
    assert serialized.get("max_walking_km") in (None, "")
