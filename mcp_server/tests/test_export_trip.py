"""export_trip MCP tool — flow tests with mocked backend.

Slice 3.5 commit 3. Single backend call: GET /trips/{id}/export?
format=json|markdown. The tool branches on format for the right
formatter:
  200 + format="markdown" → format_export_succeeded_markdown
  200 + format="json"     → format_export_succeeded_json
  404                     → format_export_failed
  401 / 422 / other       → format_export_failed (catch-all)

Four cases pinning the load-bearing routing:
1. Markdown happy: tool calls /export?format=markdown, gets text
   back, wraps with succeeded_markdown formatter (content inline).
2. JSON happy: tool calls /export?format=json, gets text back,
   wraps with succeeded_json formatter (opt-in disclosure, no
   inline JSON body per Q3 from slice opening).
3. 404 trip not found → format_export_failed surfaces reason.
4. 401 without token → tool returns _DEV_CLI_HINT (mirrors
   slice-3.3 NoTokenError pattern).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.export_trip import export_trip


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


def _fake_response(*, status_code: int, text: str, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}

    def _json() -> dict:
        import json

        return json.loads(text)

    resp.json = _json
    return resp


def _fake_client(*, get_response: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.get = MagicMock(return_value=get_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


@pytest.mark.asyncio
async def test_export_markdown_returns_succeeded_with_inline_content(
    tmp_path: Path,
) -> None:
    """Markdown branch — content is inline because Markdown renders well
    in conversation. The formatter wraps with "Here's your trip" framing
    + a `---` separator so the LLM can distinguish wrapper from content.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    md_content = "# Goa, India\n\n## Day 1\nAnjuna Beach"
    fake = _fake_client(
        get_response=_fake_response(
            status_code=200,
            text=md_content,
            headers={"content-type": "text/markdown; charset=utf-8"},
        )
    )

    with (
        patch("trip_mcp.tools.export_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.export_trip._http_client", return_value=fake),
    ):
        text = await export_trip(trip_id=trip_id, format="markdown")

    # Backend hit with format=markdown query param.
    get_args = fake.get.call_args
    assert get_args.args[0] == f"/trips/{trip_id}/export"
    params = get_args.kwargs.get("params") or {}
    assert params.get("format") == "markdown"

    # Markdown content surfaces inline.
    assert "Goa, India" in text
    assert "Anjuna Beach" in text
    # The succeeded-markdown formatter's `---` separator surfaces so the
    # LLM can distinguish wrapper text from export content.
    assert "---" in text


@pytest.mark.asyncio
async def test_export_json_returns_succeeded_with_opt_in_disclosure(
    tmp_path: Path,
) -> None:
    """JSON branch — DOES NOT inline the JSON body (would be wall-of-braces
    in conversation per slice-opening Q3). Surfaces char_count + offers
    the user the choice to see the full dump.
    """
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    json_content = '{"destination": "Goa, India", "days": []}'
    fake = _fake_client(
        get_response=_fake_response(
            status_code=200,
            text=json_content,
            headers={"content-type": "application/json"},
        )
    )

    with (
        patch("trip_mcp.tools.export_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.export_trip._http_client", return_value=fake),
    ):
        text = await export_trip(trip_id=trip_id, format="json")

    # Backend hit with format=json query param.
    params = fake.get.call_args.kwargs.get("params") or {}
    assert params.get("format") == "json"

    # JSON char_count surfaces (some humanized form).
    assert "39" in text or str(len(json_content)) in text
    # Opt-in disclosure language — does NOT inline the JSON braces.
    lower = text.lower()
    assert "want" in lower or "show" in lower or "dump" in lower
    # The raw JSON itself is NOT inline (wall-of-braces avoidance).
    assert '"destination"' not in text


@pytest.mark.asyncio
async def test_export_returns_failed_message_on_404_trip_not_found(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        get_response=_fake_response(
            status_code=404,
            text='{"detail": "trip not found"}',
            headers={"content-type": "application/json"},
        )
    )

    with (
        patch("trip_mcp.tools.export_trip._token_file", return_value=token_file),
        patch("trip_mcp.tools.export_trip._http_client", return_value=fake),
    ):
        text = await export_trip(trip_id=trip_id, format="markdown")

    assert "couldn't" in text.lower() or "could not" in text.lower()
    assert "not found" in text.lower()
    assert str(trip_id) in text
    # Must NOT contain Markdown content — this is a failure, not a success.
    assert "Day 1" not in text


@pytest.mark.asyncio
async def test_export_returns_dev_cli_hint_when_no_token_present(
    tmp_path: Path,
) -> None:
    """NoTokenError path — mirrors slice-3.3 tool pattern.
    Without a valid token file, the tool returns the dev-CLI hint
    string for setup guidance rather than calling the backend.
    """
    # Don't seed a token — the load_token raises NoTokenError.
    missing_token = tmp_path / "nonexistent"

    with patch("trip_mcp.tools.export_trip._token_file", return_value=missing_token):
        text = await export_trip(trip_id=uuid.uuid4(), format="json")

    # The DEV CLI hint is a known string mentioning the issue-mcp-token CLI.
    lower = text.lower()
    assert "token" in lower
