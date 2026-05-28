"""add_constraint MCP tool — flow tests with mocked backend.

Single backend call: POST /trips/{id}/constraints. The tool returns a
conversational "added + re-audit running" message on 202, or a failure
message on any non-202. The slice-3.4a Q3 design is mirrored here:
the underlying job IS a refine — when we say "re-audit running" the
LLM should route follow-up to get_trip (not to a fictitious "audit
status" tool).

Three load-bearing tests:
1. Happy path 202 — assert the conversational shape, presence of the
   constraint text echo, and the slice-3.3 prohibition discipline
   ("DO NOT claim 'now satisfies' the new constraint").
2. 409 (active job in flight) — failure message surfaces the slice-3.3
   KIND_LABELS label (e.g., "planning"/"refinement") so the user
   knows what's blocking.
3. 404 (trip not found) — failure message names the missing trip,
   does NOT claim the constraint was added.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.add_constraint import add_constraint


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


def _fake_client(*, post_response: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.post = MagicMock(return_value=post_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


@pytest.mark.asyncio
async def test_add_constraint_happy_path_returns_enqueued_message(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        post_response=_fake_response(
            status_code=202,
            json_payload={
                "job_id": "constraint-job-1",
                "status_url": f"/trips/{trip_id}/plan/status",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_constraint._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_constraint._http_client", return_value=fake),
    ):
        text = await add_constraint(
            trip_id=trip_id,
            constraint_text="I'm vegetarian",
            constraint_kind="dietary",
        )

    # POST hit the right URL.
    post_args = fake.post.call_args
    assert post_args.args[0] == f"/trips/{trip_id}/constraints"
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body["constraint_text"] == "I'm vegetarian"
    assert body["constraint_kind"] == "dietary"

    # Conversational shape — echoes the constraint, mentions get_trip + timing.
    assert "vegetarian" in text
    assert "get_trip" in text
    assert "10 minutes" in text or "minutes" in text.lower()

    # Slice 3.3 prohibition discipline — must NOT claim "now satisfies".
    assert "now satisfies" not in text.lower()
    assert "applied" not in text.lower()


@pytest.mark.asyncio
async def test_add_constraint_returns_failure_when_active_job_in_flight(
    tmp_path: Path,
) -> None:
    """409 path. The backend's slice-3.3 KIND_LABELS label ("planning" /
    "refinement" / "day-regeneration") appears in the detail. The MCP
    failure formatter surfaces the reason so the LLM knows why.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        post_response=_fake_response(
            status_code=409,
            json_payload={
                "detail": (
                    f"a refinement job is already in progress for trip {trip_id} "
                    f"(job refine-existing); cancel via DELETE /trips/{trip_id}/plan "
                    "before retrying"
                ),
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_constraint._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_constraint._http_client", return_value=fake),
    ):
        text = await add_constraint(
            trip_id=trip_id,
            constraint_text="I'm vegetarian",
            constraint_kind="dietary",
        )

    assert "couldn't" in text.lower() or "could not" in text.lower()
    assert "refinement" in text.lower(), "must surface the in-flight job label"
    # Must NOT claim the constraint was added on failure.
    assert "added" not in text.lower() or "couldn't" in text.lower()


@pytest.mark.asyncio
async def test_add_constraint_returns_failure_when_trip_not_found(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=404,
            json_payload={"detail": "trip not found"},
        ),
    )

    with (
        patch("trip_mcp.tools.add_constraint._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_constraint._http_client", return_value=fake),
    ):
        text = await add_constraint(
            trip_id=uuid.uuid4(),
            constraint_text="no nightclubs",
            constraint_kind="no_go",
        )

    assert "couldn't" in text.lower() or "could not" in text.lower()
    assert "not found" in text.lower()
