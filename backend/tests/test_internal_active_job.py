"""GET /internal/trips/{tripId}/active-job — Redis active_job probe.

Slice 4.2 tightening (trip-concierge-2th). The PWA detail page calls
this when /plan/status returns 404 so it can render the planning UI
even within the ~1-3s enqueue → first-JobRun-write window where the
DB has no JobRun but Redis has the active_job key.

Three tests:
  1. {active: true} when the Redis key is set
  2. {active: false} when the Redis key is absent
  3. 403 without the X-Internal-Secret header

Redis is mocked via patching the route's create_pool import — same
pattern as test_plan_endpoint.py. The internal-secret check is the
load-bearing auth surface here; the JWT/user-auth stack is not in
play for /internal/* routes.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

_INTERNAL_SECRET = "test-internal-secret-32-bytes-min"


def _mock_redis(*, value: bytes | None) -> AsyncMock:
    """Build an AsyncMock that returns `value` from get()."""
    pool = AsyncMock()
    pool.get.return_value = value
    return pool


def test_active_job_endpoint_returns_true_when_redis_key_set(
    client: TestClient,
) -> None:
    """A non-None Redis value for trip:{tripId}:active_job → active=true.
    The endpoint doesn't decode the value — it only signals presence.
    """
    trip_id = uuid.uuid4()
    pool = _mock_redis(value=b'{"job_id":"running-xyz","kind":"plan"}')

    with (
        patch("app.routes.trips._internal_secret", return_value=_INTERNAL_SECRET),
        patch("app.routes.trips.create_pool", return_value=pool),
    ):
        response = client.get(
            f"/internal/trips/{trip_id}/active-job",
            headers={"X-Internal-Secret": _INTERNAL_SECRET},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"active": True}
    # Confirm the right Redis key was probed — guard against a refactor
    # changing the key format (would silently break the planning UX).
    pool.get.assert_awaited_once_with(f"trip:{trip_id}:active_job")


def test_active_job_endpoint_returns_false_when_no_key(client: TestClient) -> None:
    """None from Redis get() → active=false. Pins the "no key" branch."""
    trip_id = uuid.uuid4()
    pool = _mock_redis(value=None)

    with (
        patch("app.routes.trips._internal_secret", return_value=_INTERNAL_SECRET),
        patch("app.routes.trips.create_pool", return_value=pool),
    ):
        response = client.get(
            f"/internal/trips/{trip_id}/active-job",
            headers={"X-Internal-Secret": _INTERNAL_SECRET},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"active": False}


def test_active_job_endpoint_requires_internal_auth(client: TestClient) -> None:
    """No header → 403. Wrong header → 403. Same response shape both ways
    (hmac.compare_digest semantics in the route handler).

    The endpoint must NOT touch Redis when auth fails — pool.get should
    never be awaited.
    """
    trip_id = uuid.uuid4()
    pool = _mock_redis(value=None)

    with (
        patch("app.routes.trips._internal_secret", return_value=_INTERNAL_SECRET),
        patch("app.routes.trips.create_pool", return_value=pool),
    ):
        # Missing header.
        resp_missing = client.get(f"/internal/trips/{trip_id}/active-job")
        # Wrong header.
        resp_wrong = client.get(
            f"/internal/trips/{trip_id}/active-job",
            headers={"X-Internal-Secret": "not-the-right-secret"},
        )

    assert resp_missing.status_code == 403
    assert resp_wrong.status_code == 403
    # Redis must not have been touched in either case — would leak a
    # network call on every unauthenticated probe.
    assert not pool.get.called
