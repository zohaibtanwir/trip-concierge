"""share_trip MCP tool — pure URL construction, no backend call.

Slice 3.5 commit 3. The tool is structurally novel in the corpus:
- No httpx.Client. No backend round-trip. No /plan/status pre-check.
- Pure function: (trip_id, state?) → response string.
- The LLM, per §4.10, calls get_trip first if unsure of state, then
  passes the state value to share_trip. share_trip routes:
    state in {None, "done", "succeeded"} → format_share_succeeded
    otherwise                              → format_share_not_ready(state)

Four cases:
1. state="done" → succeeded (URL prefix + content checks)
2. state="running" → not_ready, "still being planned" language
3. state=None default → succeeded (LLM didn't pass state)
4. URL pin: response always uses /shared/, never /trips/
   (tool-integration angle of the cross-formatter URL pin)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from trip_mcp.tools.share_trip import share_trip


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


@pytest.mark.asyncio
async def test_share_trip_done_state_returns_succeeded_message_with_url(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()

    with patch("trip_mcp.tools.share_trip._token_file", return_value=token_file):
        text = await share_trip(trip_id=trip_id, state="done")

    # URL surfaces with the trip_id.
    assert str(trip_id) in text
    # Share-by-URL framing is present so the LLM tells the user the right thing.
    lower = text.lower()
    assert "share" in lower or "anyone with this link" in lower
    # Honest broken — no revocation promise (slice 3.5 v1.0a privacy model).
    assert "doesn't expire" in lower or "doesn't support revoking" in lower


@pytest.mark.asyncio
async def test_share_trip_running_state_returns_not_ready_clarification(
    tmp_path: Path,
) -> None:
    """state-aware branch: matches format_regenerate_day_not_ready
    structure verbatim per slice-3.3 corpus consistency.
    """
    token_file = _seed_token(tmp_path)

    with patch("trip_mcp.tools.share_trip._token_file", return_value=token_file):
        text = await share_trip(trip_id=uuid.uuid4(), state="running")

    lower = text.lower()
    # "Still being planned" or equivalent — corpus-aligned with slice 3.3.
    assert "still being planned" in lower or "still planning" in lower
    # Routes user to get_trip for the next check.
    assert "get_trip" in text
    # Does NOT include the URL (the not-ready branch is a clarification, not a share).
    assert "tripconcierge.app" not in text


@pytest.mark.asyncio
async def test_share_trip_default_no_state_returns_succeeded_path(
    tmp_path: Path,
) -> None:
    """When the LLM is confident the trip is ready, it MAY omit state.
    Tool defaults to succeeded behavior — same as state="done" explicitly.
    Pinning so a future "always require state" change is deliberate.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()

    with patch("trip_mcp.tools.share_trip._token_file", return_value=token_file):
        text = await share_trip(trip_id=trip_id)  # no state arg

    assert str(trip_id) in text
    assert "tripconcierge.app" in text


@pytest.mark.asyncio
async def test_share_trip_response_url_uses_shared_prefix_not_trips_prefix(
    tmp_path: Path,
) -> None:
    """Tool-integration angle of the cross-formatter URL pin.

    Sister tests in test_responses.py pin (a) the _share_url helper
    and (b) format_created_trip + format_share_succeeded agreement.
    This test pins the end-to-end tool-output level — catches a
    "helper was updated but the tool still hardcodes /trips/" mistake.
    """
    token_file = _seed_token(tmp_path)

    with patch("trip_mcp.tools.share_trip._token_file", return_value=token_file):
        text = await share_trip(trip_id=uuid.uuid4(), state="done")

    assert "https://tripconcierge.app/shared/" in text, (
        "share_trip tool output must use /shared/ URL prefix per slice 3.5. "
        "If you see /trips/ in the output, the _share_url helper or its "
        "callers regressed — see test_responses.py URL-pin tests."
    )
    assert "/trips/" not in text
