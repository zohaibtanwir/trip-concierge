"""refine_trip MCP tool — flow tests with mocked backend.

Single backend call: POST /trips/{id}/refine. Returns 202 with job_id
on success; surfaces 404/409/etc. as failure messages.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.refine_trip import refine_trip


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


def _fake_client_with(post_response: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.post = MagicMock(return_value=post_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


@pytest.mark.asyncio
async def test_refine_trip_happy_path_returns_enqueued_message(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake_client = _fake_client_with(
        _fake_response(
            status_code=202,
            json_payload={"job_id": "refine-1", "status_url": f"/trips/{trip_id}/plan/status"},
        )
    )

    with (
        patch("trip_mcp.tools.refine_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.refine_trip._http_client", return_value=fake_client),
    ):
        text = await refine_trip(
            trip_id=trip_id,
            refinement_description="make Day 2 chiller and add more food",
        )

    # The LLM consumes this text — load-bearing phrasings.
    assert "10 minutes" in text or "10-minute" in text or "few minutes" in text.lower()
    assert "get_trip" in text
    # Don't claim ready — slice 3.2 prohibition discipline.
    assert "ready" not in text.lower()
    assert "applied" not in text.lower()
    assert "done" not in text.lower()
    # POST hit the right URL.
    post_args = fake_client.post.call_args
    assert post_args.args[0] == f"/trips/{trip_id}/refine"
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body["refinement_description"].startswith("make Day 2")


@pytest.mark.asyncio
async def test_refine_trip_404_returns_clear_failure_message(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    fake_client = _fake_client_with(
        _fake_response(status_code=404, json_payload={"detail": "trip not found"})
    )

    with (
        patch("trip_mcp.tools.refine_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.refine_trip._http_client", return_value=fake_client),
    ):
        text = await refine_trip(trip_id=uuid.uuid4(), refinement_description="anything")

    assert "couldn't" in text.lower() or "not found" in text.lower() or "could not" in text.lower()


@pytest.mark.asyncio
async def test_refine_trip_no_token_no_email_returns_setup_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 4.1b: replaces the dev-CLI hint with the env-var setup hint."""
    monkeypatch.delenv("TC_MCP_USER_EMAIL", raising=False)
    missing = tmp_path / "absent"
    with patch("trip_mcp.tools.refine_trip._token_file", return_value=missing):
        text = await refine_trip(trip_id=uuid.uuid4(), refinement_description="anything")
    assert "TC_MCP_USER_EMAIL" in text
    assert "tc-issue-mcp-token" not in text
