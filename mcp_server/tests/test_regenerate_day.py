"""regenerate_day MCP tool — flow tests with mocked backend.

Two HTTP calls per invocation:
  1. GET /trips/{id}/plan/status   — gate-check (refuses on non-ready)
  2. POST /trips/{id}/days/{n}/regenerate — enqueue (only if status=done)

The gate-check is the load-bearing UX: it spares the user a confusing
clarification round-trip by surfacing "trip not ready" before any
backend enqueue work.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.regenerate_day import regenerate_day


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


def _fake_client(
    *,
    status_response: MagicMock | None = None,
    post_response: MagicMock | None = None,
) -> MagicMock:
    fake = MagicMock()
    fake.get = MagicMock(return_value=status_response)
    fake.post = MagicMock(return_value=post_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


def _status(state: str) -> dict:
    return {
        "state": state,
        "job_id": None,
        "kind": None,
        "approved": True if state == "done" else None,
        "progress_message": None,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "trip_url": "/trips/x",
    }


@pytest.mark.asyncio
async def test_regenerate_day_on_ready_trip_enqueues_and_returns_message(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        status_response=_fake_response(status_code=200, json_payload=_status("done")),
        post_response=_fake_response(
            status_code=202,
            json_payload={"job_id": "regen-1", "status_url": f"/trips/{trip_id}/plan/status"},
        ),
    )

    with (
        patch("trip_mcp.tools.regenerate_day._token_file", return_value=token_file),
        patch("trip_mcp.tools.regenerate_day._http_client", return_value=fake),
    ):
        text = await regenerate_day(trip_id=trip_id, day_number=2, hint="more food")

    # Status check happened first.
    assert fake.get.called, "must GET /plan/status before enqueueing"
    # POST hit the right URL with day_number in path.
    post_args = fake.post.call_args
    assert post_args.args[0] == f"/trips/{trip_id}/days/2/regenerate"
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body.get("hint") == "more food"

    # Response is conversational, mentions get_trip + timing.
    assert "get_trip" in text
    assert "minutes" in text.lower()
    # Slice 3.2 prohibition discipline.
    assert "ready" not in text.lower()
    assert "applied" not in text.lower()
    assert "done" not in text.lower()


@pytest.mark.asyncio
async def test_regenerate_day_on_failed_trip_refuses_without_post(tmp_path: Path) -> None:
    """The slice-thesis test for regen: when status=failed, the tool refuses
    BEFORE any backend enqueue, surfacing a clarification the LLM echoes
    to the user.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        status_response=_fake_response(status_code=200, json_payload=_status("failed")),
        post_response=_fake_response(status_code=202, json_payload={"job_id": "should-not-fire"}),
    )

    with (
        patch("trip_mcp.tools.regenerate_day._token_file", return_value=token_file),
        patch("trip_mcp.tools.regenerate_day._http_client", return_value=fake),
    ):
        text = await regenerate_day(trip_id=uuid.uuid4(), day_number=2)

    assert not fake.post.called, "must NOT POST when status=failed"
    assert "create_trip" in text or "refine_trip" in text
    # Names the failure plainly — no softer language.
    for softer in ("almost there", "still working", "not quite finished"):
        assert softer not in text.lower()


@pytest.mark.asyncio
async def test_regenerate_day_on_planning_trip_refuses_with_check_back_message(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        status_response=_fake_response(status_code=200, json_payload=_status("running")),
        post_response=_fake_response(status_code=202, json_payload={"job_id": "no"}),
    )

    with (
        patch("trip_mcp.tools.regenerate_day._token_file", return_value=token_file),
        patch("trip_mcp.tools.regenerate_day._http_client", return_value=fake),
    ):
        text = await regenerate_day(trip_id=uuid.uuid4(), day_number=1)

    assert not fake.post.called, "must NOT POST when status=running"
    assert "get_trip" in text
    # Conveys "still being planned" or "in progress".
    lower = text.lower()
    assert "still" in lower or "progress" in lower or "planned" in lower
