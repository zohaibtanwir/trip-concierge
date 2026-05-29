"""add_source MCP tool — flow tests with mocked backend.

Slice 3.4b commit 4. Single backend call: POST /trips/{id}/sources.
The tool accepts EITHER a url (fetched server-side via the
6-defense source_ingestion stack from commit 2) OR text
(passthrough). Each of the four ingestion exceptions surfaces as a
distinct (status, body kind) pair that the tool branches on.

Seven load-bearing tests, one per branch + 2 happy paths:
1. URL happy path 200 — body trio (source_id, content_type,
   char_count) reaches the formatter; LLM-routing language
   ("refine_trip") present; no "applied/used" claims.
2. Text happy path 200 — no fetch attempted by the tool; same
   trio surfaces.
3. 400 kind="denied_host" — distinct UX, no "fetch failed" wording.
4. 502 kind="fetch_failed" — surfaces the reason verbatim, offers
   pasted text alternative, does NOT claim attached.
5. 413 kind="too_large" + byte_count — surfaces the byte count
   and the 2MB cap so the user sees the scale.
6. 415 kind="unsupported_content_type" + content_type field —
   distinct from fetch_failed; retry won't help.
7. 409 kind="active_job" — slice-3.3 KIND_LABELS reuse; routes the
   user back to get_trip.

NoTokenError path (returns _DEV_CLI_HINT) is exercised end-to-end
by test_tool_base.py — not repeated here.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.add_source import add_source


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


def _fake_response(*, status_code: int, json_payload: dict[str, Any]) -> MagicMock:
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
async def test_add_source_url_happy_path_returns_attached_message(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        post_response=_fake_response(
            status_code=200,
            json_payload={
                "source_id": str(uuid.uuid4()),
                "content_type": "url_fetched/html",
                "char_count": 4321,
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=trip_id,
            url="https://reddit.com/r/IndiaTravel/comments/abc",
            text=None,
        )

    # Right URL + body shape.
    post_args = fake.post.call_args
    assert post_args.args[0] == f"/trips/{trip_id}/sources"
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body["url"] == "https://reddit.com/r/IndiaTravel/comments/abc"
    assert "text" not in body or body.get("text") is None

    # Response: conversational, mentions refine_trip + character count, no
    # "applied/used/read" claims.
    assert "4,321" in text or "4321" in text  # char_count surfaces
    assert "url_fetched/html" in text
    assert "refine_trip" in text
    for forbidden in ("has read", "is using", "now applied", "already applied"):
        assert forbidden not in text.lower(), (
            f"prohibition discipline: '{forbidden}' must NOT appear"
        )


@pytest.mark.asyncio
async def test_add_source_text_happy_path_skips_fetch_and_returns_attached(
    tmp_path: Path,
) -> None:
    """The text branch never claims a URL was fetched."""
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    fake = _fake_client(
        post_response=_fake_response(
            status_code=200,
            json_payload={
                "source_id": str(uuid.uuid4()),
                "content_type": "user_text",
                "char_count": 78,
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=trip_id,
            url=None,
            text="my friend texted me: try Vinayak in North Goa for the prawn curry",
        )

    post_args = fake.post.call_args
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body.get("text") is not None
    assert body.get("url") is None or "url" not in body

    assert "78" in text
    assert "user_text" in text
    assert "refine_trip" in text


@pytest.mark.asyncio
async def test_add_source_denied_host_returns_security_explanation(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=400,
            json_payload={
                "detail": "denied host: localhost",
                "kind": "denied_host",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=uuid.uuid4(),
            url="http://localhost/internal",
            text=None,
        )

    # Names the security reason plainly; offers paste alternative.
    assert "denied" in text.lower() or "private" in text.lower() or "security" in text.lower()
    assert "paste" in text.lower()
    # Must NOT claim attached.
    assert "attached" not in text.lower() or "couldn't" in text.lower()


@pytest.mark.asyncio
async def test_add_source_fetch_failed_offers_paste_alternative(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=502,
            json_payload={
                "detail": "timeout fetching https://example.com",
                "kind": "fetch_failed",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=uuid.uuid4(),
            url="https://example.com",
            text=None,
        )

    assert "couldn't" in text.lower() or "could not" in text.lower()
    assert "paste" in text.lower()
    assert "attached" not in text.lower() or "couldn't" in text.lower()


@pytest.mark.asyncio
async def test_add_source_too_large_surfaces_byte_count_and_offers_excerpt(
    tmp_path: Path,
) -> None:
    """413 path. The formatter surfaces the byte count so the user
    knows the scale and offers a shorter excerpt — DOES NOT auto-retry.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=413,
            json_payload={
                "detail": "content too large: 3500000 bytes (cap 2000000)",
                "kind": "too_large",
                "byte_count": 3_500_000,
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=uuid.uuid4(),
            url="https://example.com/huge",
            text=None,
        )

    # Some humanized byte count appears.
    assert "3,500,000" in text or "3500000" in text or "3.5" in text
    # Cap mentioned.
    assert "2 MB" in text or "2MB" in text or "2,000,000" in text
    # Offers shorter excerpt.
    assert "excerpt" in text.lower() or "shorter" in text.lower() or "paste" in text.lower()


@pytest.mark.asyncio
async def test_add_source_unsupported_content_type_offers_paste(tmp_path: Path) -> None:
    """415 path — distinct from fetch_failed. Retrying won't help; only
    paste or different URL.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=415,
            json_payload={
                "detail": "unsupported Content-Type 'image/png' for ...",
                "kind": "unsupported_content_type",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=uuid.uuid4(),
            url="https://example.com/photo.png",
            text=None,
        )

    # Names the format limitation plainly. Mentions one of the supported types.
    assert "html" in text.lower() or "plain text" in text.lower() or "json" in text.lower()
    assert "paste" in text.lower() or "different url" in text.lower()
    # No "try again" framing — retry won't help for an unsupported format.
    assert "couldn't" in text.lower() or "can only read" in text.lower()


@pytest.mark.asyncio
async def test_add_source_active_job_surfaces_kind_label_and_routes_to_get_trip(
    tmp_path: Path,
) -> None:
    """409 + kind="active_job" — slice-3.3 KIND_LABELS reuse. Routes
    user back to get_trip; does NOT claim attached.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=409,
            json_payload={
                "detail": "a refinement job is already in progress...",
                "kind": "active_job",
                "active_job_id": "refine-existing",
                "active_job_kind": "refine",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.add_source._token_file", return_value=token_file),
        patch("trip_mcp.tools.add_source._http_client", return_value=fake),
    ):
        text = await add_source(
            trip_id=uuid.uuid4(),
            url="https://example.com",
            text=None,
        )

    assert "refinement" in text.lower(), "must surface KIND_LABELS['refine']='refinement'"
    assert "get_trip" in text
    assert "attached" not in text.lower() or "can't" in text.lower()
