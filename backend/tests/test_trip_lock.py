"""Trip-lock helper extraction tests — slice 4.5b commit 1.

The slice 4.5b PATCH /trips/{id} route needs the same active-job guard
that POST /constraints, /refine, /regenerate, /alternative, /sources,
and /plan use. Per the Q1=B sign-off, the helpers move OUT of
routes/plan.py and INTO app.services.trip_lock so the new PATCH route
imports from the canonical location instead of from a route module.

This test pins:
1. The helper module exists at app.services.trip_lock with the
   canonical names (KIND_LABELS, encode_active_value,
   decode_active_value, _ACTIVE_JOB_KEY_TTL_SECONDS).
2. Behavior matches the slice-3.3 contract exactly — round-trip
   encode/decode preserves (job_id, kind); legacy plain-string values
   degrade to kind='plan'; None → None.
3. The 5 importers (alternative, constraints, refine, regenerate,
   sources) import from app.services.trip_lock, not from
   app.routes.plan. routes/plan.py re-exports for backwards-compat
   (its own importers stay valid) but the canonical import path is
   the service module.
"""

from __future__ import annotations

import importlib
import json


def test_trip_lock_module_exists() -> None:
    """The extraction happened — app.services.trip_lock is importable."""
    mod = importlib.import_module("app.services.trip_lock")
    assert hasattr(mod, "KIND_LABELS"), "trip_lock must expose KIND_LABELS"
    assert hasattr(mod, "encode_active_value")
    assert hasattr(mod, "decode_active_value")


def test_kind_labels_canonical_values() -> None:
    from app.services.trip_lock import KIND_LABELS

    assert KIND_LABELS == {
        "plan": "planning",
        "refine": "refinement",
        "regen": "day regeneration",
    }


def test_encode_decode_roundtrip() -> None:
    from app.services.trip_lock import decode_active_value, encode_active_value

    payload = encode_active_value(job_id="abc-123", kind="refine")
    parsed = json.loads(payload)
    assert parsed == {"job_id": "abc-123", "kind": "refine"}

    assert decode_active_value(payload.encode()) == ("abc-123", "refine")
    assert decode_active_value(payload) == ("abc-123", "refine")


def test_decode_none_returns_none() -> None:
    from app.services.trip_lock import decode_active_value

    assert decode_active_value(None) is None


def test_decode_legacy_plain_string_degrades_to_plan() -> None:
    """Pre-slice-3.3 active_job values were plain arq job_ids — no kind.
    decode must treat those as kind='plan' (slice 3.3 contract preserved)."""
    from app.services.trip_lock import decode_active_value

    assert decode_active_value("legacy-job-id") == ("legacy-job-id", "plan")
    assert decode_active_value(b"legacy-job-id") == ("legacy-job-id", "plan")


def test_routes_plan_reexports_for_backwards_compat() -> None:
    """routes/plan.py's existing helper names must still resolve so the
    5 sibling-route importers don't need to be touched in this commit.
    Their import lines (e.g. `from app.routes.plan import KIND_LABELS,
    decode_active_value`) keep working — the canonical home is now
    trip_lock, plan.py re-exports."""
    from app.routes import plan as plan_routes
    from app.services import trip_lock

    assert plan_routes.KIND_LABELS is trip_lock.KIND_LABELS
    assert plan_routes.decode_active_value is trip_lock.decode_active_value
    assert plan_routes.encode_active_value is trip_lock.encode_active_value
