"""get_trip MCP tool — flow tests with mocked backend.

The tool makes two HTTP calls per invocation:
  1. GET /trips/{id}/full        — content (days/blocks/sources)
  2. GET /trips/{id}/plan/status — lifecycle state

Two calls keeps each backend endpoint a pure read with no Redis coupling
(same pattern as slice 3.2's POST /trips + POST /plan two-call flow).

Each test patches the tool's _http_client indirection so no real network
is touched. The load-bearing assertion is the response *text shape* —
the LLM consumes that text directly and must NOT soften "failed" into
optimistic language. See test_failed_state_does_not_soften_language.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.get_trip import get_trip


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


def _fake_response(*, status_code: int, json_payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    return resp


def _fake_client_with(responses_by_path: dict[str, MagicMock]) -> MagicMock:
    """Return a MagicMock that acts like an httpx.Client. GET routes by path."""
    fake = MagicMock()

    def _get(path: str) -> MagicMock:
        for prefix, resp in responses_by_path.items():
            if path.startswith(prefix):
                return resp
        raise AssertionError(f"unexpected GET: {path}")

    fake.get = _get
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


def _full_trip_payload(trip_id: uuid.UUID, *, with_days: bool = True) -> dict:
    days: list[dict] = []
    if with_days:
        days = [
            {
                "id": str(uuid.uuid4()),
                "day_number": 1,
                "date": "2026-07-15",
                "summary": "Beach day",
                "blocks": [
                    {
                        "id": str(uuid.uuid4()),
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Anjuna Beach",
                        "duration_minutes": 120,
                        "start_time": "09:00",
                        "est_cost": "0.00",
                        "currency": "INR",
                        "locked": False,
                        "notes": "",
                        "lat": None,
                        "lng": None,
                        "sources": [],
                    },
                ],
            },
        ]
    return {
        "id": str(trip_id),
        "user_id": str(uuid.uuid4()),
        "status": "draft",
        "destination": "Goa, India",
        "start_date": None,
        "end_date": None,
        "group_size": 1,
        "budget_total": None,
        "currency": "INR",
        "constraints": {},
        "pace": "balanced",
        "created_at": "2026-05-28T12:00:00+00:00",
        "updated_at": "2026-05-28T12:00:00+00:00",
        "days": days,
    }


def _status_payload(state: str, *, error: str | None = None) -> dict:
    return {
        "state": state,
        "job_id": "job-x",
        "kind": "plan",
        "approved": None,
        "progress_message": None,
        "error": error,
        "started_at": None,
        "finished_at": None,
        "trip_url": f"/trips/{uuid.uuid4()}",
    }


@pytest.mark.asyncio
async def test_get_trip_planning_state_reports_in_progress(tmp_path: Path) -> None:
    """When status=running, the tool tells the user it's in progress.
    No fabricated venues — Days array may exist from a prior run but the
    response must focus on the planning signal.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake_client = _fake_client_with(
        {
            f"/trips/{trip_id}/full": _fake_response(
                status_code=200, json_payload=_full_trip_payload(trip_id, with_days=False)
            ),
            f"/trips/{trip_id}/plan/status": _fake_response(
                status_code=200,
                json_payload=_status_payload("running"),
            ),
        }
    )

    with (
        patch("trip_mcp.tools.get_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.get_trip._http_client", return_value=fake_client),
    ):
        text = await get_trip(trip_id=trip_id)

    assert "Goa" in text
    assert "progress" in text.lower() or "still" in text.lower()
    # No "ready" claim — slice 3.2 prohibition discipline.
    assert "ready" not in text.lower()
    assert "done" not in text.lower()


@pytest.mark.asyncio
async def test_get_trip_ready_state_summarizes_actual_days(tmp_path: Path) -> None:
    """When state=done and approved=true, the tool summarizes the real
    days/blocks data — no embellishment, but real venue names show up.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake_client = _fake_client_with(
        {
            f"/trips/{trip_id}/full": _fake_response(
                status_code=200, json_payload=_full_trip_payload(trip_id, with_days=True)
            ),
            f"/trips/{trip_id}/plan/status": _fake_response(
                status_code=200,
                json_payload={**_status_payload("done"), "approved": True},
            ),
        }
    )

    with (
        patch("trip_mcp.tools.get_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.get_trip._http_client", return_value=fake_client),
    ):
        text = await get_trip(trip_id=trip_id)

    # Real venue from the data, not invented.
    assert "Anjuna Beach" in text
    assert "Day 1" in text


@pytest.mark.asyncio
async def test_get_trip_failed_state_does_not_soften_language(tmp_path: Path) -> None:
    """The slice-thesis test. When status=failed, the response must:
    (1) report failure plainly — name "failed" or "didn't complete"
    (2) NOT contain any of the forbidden softer phrases
    (3) suggest next steps the user can act on
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake_client = _fake_client_with(
        {
            f"/trips/{trip_id}/full": _fake_response(
                status_code=200, json_payload=_full_trip_payload(trip_id, with_days=False)
            ),
            f"/trips/{trip_id}/plan/status": _fake_response(
                status_code=200,
                json_payload=_status_payload(
                    "failed", error="ValidationError: 1 validation error for TripPlan"
                ),
            ),
        }
    )

    with (
        patch("trip_mcp.tools.get_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.get_trip._http_client", return_value=fake_client),
    ):
        text = await get_trip(trip_id=trip_id)

    lower = text.lower()
    assert "failed" in lower or "didn't complete" in lower, "failed state must be reported plainly"
    for softer in ("almost there", "still working", "not quite finished"):
        assert softer not in lower, f"forbidden softer phrase {softer!r} leaked"
    # Next-step suggestion.
    assert "create_trip" in text or "try again" in lower or "refine_trip" in text


@pytest.mark.asyncio
async def test_get_trip_returns_404_message_when_trip_unknown(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake_client = _fake_client_with(
        {
            f"/trips/{trip_id}/full": _fake_response(
                status_code=404, json_payload={"detail": "trip not found"}
            ),
        }
    )

    with (
        patch("trip_mcp.tools.get_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.get_trip._http_client", return_value=fake_client),
    ):
        text = await get_trip(trip_id=trip_id)

    assert "couldn't find" in text.lower() or "not found" in text.lower()


@pytest.mark.asyncio
async def test_get_trip_no_token_no_email_returns_setup_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 4.1b: replaces the dev-CLI hint with the env-var setup hint."""
    monkeypatch.delenv("TC_MCP_USER_EMAIL", raising=False)
    missing = tmp_path / "absent"
    with patch("trip_mcp.tools.get_trip._token_file", return_value=missing):
        text = await get_trip(trip_id=uuid.uuid4())
    assert "TC_MCP_USER_EMAIL" in text
    assert "tc-issue-mcp-token" not in text
