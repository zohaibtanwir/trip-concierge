"""create_trip MCP tool — flow tests with mocked backend.

The tool makes two HTTP calls per invocation (POST /trips then POST
/trips/{id}/plan). Each test patches `httpx.Client` so no real network
is touched. The token-file fixture lives in tmp_path so the @requires_auth
decorator sees a token without depending on the dev's real ~/.config.

The load-bearing assertion in each test is the response *text shape* —
not just "succeeded" but "what does the LLM see?" That text is the
product surface.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.create_trip import create_trip


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


def _fake_response(*, status_code: int, json_payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


@pytest.mark.asyncio
async def test_happy_path_returns_conversational_message_with_share_url(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()

    posts: list[tuple[str, dict | None]] = []

    def _post(url: str, json: dict | None = None) -> MagicMock:
        posts.append((url, json))
        if url == "/trips":
            return _fake_response(
                status_code=201,
                json_payload={
                    "id": str(trip_id),
                    "user_id": str(uuid.uuid4()),
                    "destination": "Goa",
                    "status": "draft",
                    "start_date": None,
                    "end_date": None,
                    "group_size": 2,
                    "budget_total": "40000.00",
                    "currency": "INR",
                    "constraints": {},
                    "pace": "balanced",
                    "created_at": "2026-05-27T18:00:00+00:00",
                    "updated_at": "2026-05-27T18:00:00+00:00",
                },
            )
        if url.endswith("/plan"):
            return _fake_response(
                status_code=202,
                json_payload={
                    "job_id": "abc123",
                    "status_url": f"/trips/{trip_id}/plan/status",
                },
            )
        raise AssertionError(f"unexpected POST: {url}")

    fake_client = MagicMock()
    fake_client.post = _post
    fake_client.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake_client.__exit__ = lambda self, *a: None  # type: ignore[method-assign]

    with (
        patch("trip_mcp.tools.create_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.create_trip._http_client", return_value=fake_client),
    ):
        text = await create_trip(
            destination="Goa",
            budget_total=40000,
            currency="INR",
            group_size=2,
        )

    # Two POSTs happened in the right order against the right URLs.
    assert [p[0] for p in posts] == ["/trips", f"/trips/{trip_id}/plan"]
    # Response is conversational and load-bearing strings are present.
    assert str(trip_id) in text
    assert "Goa" in text
    assert "10 minutes" in text
    assert "https://" in text or "/trips/" in text  # share URL


@pytest.mark.asyncio
async def test_create_trip_failure_surfaces_clear_error(tmp_path: Path) -> None:
    """POST /trips fails server-side (e.g. backend rule we don't enforce
    client-side). The tool must surface an error string Claude Desktop
    renders directly — not a raw exception.

    Input must pass the client-side CreateTripInput validator first so
    we actually reach the HTTP layer; the model's cross-field rule
    catches the empty-destination case before any POST happens (see
    the clarification-path test above).
    """
    token_file = _seed_token(tmp_path)

    def _post(url: str, json: dict | None = None) -> MagicMock:
        return _fake_response(
            status_code=422,
            json_payload={
                "detail": [{"loc": ["body", "start_date"], "msg": "invalid date format"}]
            },
        )

    fake_client = MagicMock()
    fake_client.post = _post
    fake_client.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake_client.__exit__ = lambda self, *a: None  # type: ignore[method-assign]

    with (
        patch("trip_mcp.tools.create_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.create_trip._http_client", return_value=fake_client),
    ):
        text = await create_trip(destination="Goa")

    # Don't leak the raw exception; do convey that the create failed.
    assert "trip" in text.lower()
    assert "could not" in text.lower() or "couldn't" in text.lower() or "failed" in text.lower()


@pytest.mark.asyncio
async def test_plan_enqueue_failure_returns_partial_failure_message(
    tmp_path: Path,
) -> None:
    """POST /trips succeeds (201), POST /plan fails. Tool returns the
    canonical partial-failure string from _responses.format_partial_failure.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()

    def _post(url: str, json: dict | None = None) -> MagicMock:
        if url == "/trips":
            return _fake_response(
                status_code=201,
                json_payload={
                    "id": str(trip_id),
                    "user_id": str(uuid.uuid4()),
                    "destination": "Goa",
                    "status": "draft",
                    "start_date": None,
                    "end_date": None,
                    "group_size": 1,
                    "budget_total": None,
                    "currency": "USD",
                    "constraints": {},
                    "pace": "balanced",
                    "created_at": "2026-05-27T18:00:00+00:00",
                    "updated_at": "2026-05-27T18:00:00+00:00",
                },
            )
        if url.endswith("/plan"):
            return _fake_response(
                status_code=500,
                json_payload={"detail": "redis unavailable"},
            )
        raise AssertionError(f"unexpected POST: {url}")

    fake_client = MagicMock()
    fake_client.post = _post
    fake_client.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake_client.__exit__ = lambda self, *a: None  # type: ignore[method-assign]

    with (
        patch("trip_mcp.tools.create_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.create_trip._http_client", return_value=fake_client),
    ):
        text = await create_trip(destination="Goa")

    # Canonical partial-failure phrasing (from _responses.format_partial_failure).
    assert str(trip_id) in text
    assert "couldn't be started" in text or "could not be started" in text
    assert "start planning again" in text.lower() or "retry" in text.lower()
    assert "10 minutes" not in text  # the job did NOT start


@pytest.mark.asyncio
async def test_create_trip_with_neither_destination_nor_vibe_asks_for_clarification(
    tmp_path: Path,
) -> None:
    """The "at least one of destination or vibe" rule fires before the
    HTTP layer is touched. The tool returns the clarification message
    instead of making any backend calls.
    """
    token_file = _seed_token(tmp_path)

    fake_client = MagicMock()
    fake_client.post = MagicMock(side_effect=AssertionError("must not POST"))
    fake_client.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake_client.__exit__ = lambda self, *a: None  # type: ignore[method-assign]

    with (
        patch("trip_mcp.tools.create_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.create_trip._http_client", return_value=fake_client),
    ):
        text = await create_trip(destination=None, vibe=None)

    # No HTTP call happened — validation short-circuited.
    assert not fake_client.post.called, (
        "validation must short-circuit before any backend HTTP calls"
    )
    # Surfaces the canonical clarification message.
    assert "destination" in text.lower()
    assert "vibe" in text.lower()
    assert "What did you have in mind?" in text


@pytest.mark.asyncio
async def test_create_trip_no_token_no_email_returns_setup_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 4.1b: with no token AND no TC_MCP_USER_EMAIL configured,
    the tool returns the env-var setup hint (replaces the dev-CLI hint
    that landed in slice 3.1)."""
    monkeypatch.delenv("TC_MCP_USER_EMAIL", raising=False)
    missing_file = tmp_path / "absent"
    with patch("trip_mcp.tools.create_trip._token_file", return_value=missing_file):
        text = await create_trip(destination="Goa")
    assert "TC_MCP_USER_EMAIL" in text
    # The old dev-CLI hint must NOT come back — pin the migration.
    assert "tc-issue-mcp-token" not in text
