"""Pending-challenge state machine — slice 4.1b (0h0).

_ensure_challenge_resolved drives the per-tool-call flow. Module-level
state holds the in-flight challenge between calls (the stdio MCP
server is single-connection by design, so global state is safe; see
challenges.py docstring + the v2.0 followup if we ever go multi-connection).

Five branches tested:
1. No _pending + TC_MCP_USER_EMAIL set → POST /challenge, store,
   return ChallengeState(magic_link_url=...).
2. No _pending + TC_MCP_USER_EMAIL missing → no backend call, return
   ChallengeState(magic_link_url=None) so the decorator surfaces the
   env-var-missing hint.
3. _pending + poll returns status=pending → return same URL, no
   second POST to /challenge (waiting for user to click).
4. _pending + poll returns status=redeemed → return
   ChallengeState(redeemed=True, mcp_token=jwt), clear _pending.
5. _pending + poll returns 410 → clear _pending, then behave as
   branch 1 or 2 (re-evaluate fresh).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Module-state reset moved to conftest.py so the autouse fixture covers
# ALL tests, not just tests inside this file. Tool tests previously
# inherited stale _pending state and hit ConnectError on CI.


def _fake_client_with_response(*, status_code: int, json_payload: dict | None = None) -> MagicMock:
    """Build a fake httpx.Client-shaped context manager. Matches the
    pattern used by `unauthed_client()` in http_client.py.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload or {}

    client = MagicMock()
    client.post = MagicMock(return_value=resp)
    client.get = MagicMock(return_value=resp)
    client.__enter__ = lambda self: self  # type: ignore[method-assign]
    client.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_no_pending_email_set_posts_challenge_stores_pending_returns_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch 1: fresh state + email configured → /challenge POST, store
    pending, return ChallengeState with magic_link_url."""
    from trip_mcp import challenges

    monkeypatch.setenv("TC_MCP_USER_EMAIL", "u@example.com")
    fake = _fake_client_with_response(
        status_code=200,
        json_payload={
            "code": "abcDEF12345678ZZZZZZZZ",
            "poll_url": "https://backend.example.com/auth/mcp/poll/abcDEF12345678ZZZZZZZZ",
            "expires_at": "2026-06-04T18:00:00+00:00",
        },
    )

    with patch("trip_mcp.challenges.unauthed_client", return_value=fake):
        state = await challenges._ensure_challenge_resolved()

    assert state.redeemed is False
    assert state.mcp_token is None
    assert state.magic_link_url is not None
    assert "abcDEF12345678ZZZZZZZZ" in state.magic_link_url
    assert "/auth/mcp/redeem?code=" in state.magic_link_url

    # POST hit /challenge with the email.
    fake.post.assert_called_once()
    args, kwargs = fake.post.call_args
    assert args[0] == "/auth/mcp/challenge"
    assert kwargs["json"]["email"] == "u@example.com"

    # _pending now stores the code so subsequent calls poll instead of re-POSTing.
    assert challenges._pending is not None
    assert challenges._pending.code == "abcDEF12345678ZZZZZZZZ"


@pytest.mark.asyncio
async def test_no_pending_email_missing_returns_none_url_no_backend_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch 2: fresh state + no TC_MCP_USER_EMAIL → no backend call,
    return ChallengeState(magic_link_url=None). The decorator uses
    this signal to render the "set TC_MCP_USER_EMAIL" config hint.
    """
    from trip_mcp import challenges

    monkeypatch.delenv("TC_MCP_USER_EMAIL", raising=False)
    fake = _fake_client_with_response(status_code=200)

    with patch("trip_mcp.challenges.unauthed_client", return_value=fake):
        state = await challenges._ensure_challenge_resolved()

    assert state.redeemed is False
    assert state.magic_link_url is None
    fake.post.assert_not_called()
    fake.get.assert_not_called()
    assert challenges._pending is None


@pytest.mark.asyncio
async def test_pending_poll_returns_pending_returns_same_url_no_new_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch 3: _pending exists + backend reports status=pending →
    return SAME magic_link_url (the user just hasn't clicked yet), do
    NOT POST a new /challenge."""
    from trip_mcp import challenges

    monkeypatch.setenv("TC_MCP_USER_EMAIL", "u@example.com")
    challenges._store_pending(
        code="existing-code-aaaaaaa",
        magic_link_url="https://x.example/redeem?code=existing-code-aaaaaaa",
    )

    fake = _fake_client_with_response(
        status_code=200,
        json_payload={
            "status": "pending",
            "mcp_token": None,
            "expires_at": "2026-06-04T18:00:00+00:00",
        },
    )

    with patch("trip_mcp.challenges.unauthed_client", return_value=fake):
        state = await challenges._ensure_challenge_resolved()

    assert state.redeemed is False
    assert state.magic_link_url == "https://x.example/redeem?code=existing-code-aaaaaaa"

    # We polled, we did not re-POST /challenge.
    fake.get.assert_called_once()
    fake.post.assert_not_called()

    # _pending preserved across the call.
    assert challenges._pending is not None
    assert challenges._pending.code == "existing-code-aaaaaaa"


@pytest.mark.asyncio
async def test_pending_poll_returns_redeemed_returns_token_clears_pending() -> None:
    """Branch 4: _pending + poll → status=redeemed → return
    ChallengeState(redeemed=True, mcp_token=jwt) and clear _pending so
    the next tool call doesn't re-poll a now-consumed code."""
    from trip_mcp import challenges

    challenges._store_pending(
        code="ready-to-redeem-aaaa",
        magic_link_url="https://x.example/redeem?code=ready-to-redeem-aaaa",
    )

    fake = _fake_client_with_response(
        status_code=200,
        json_payload={
            "status": "redeemed",
            "mcp_token": "fake.jwt.token.string",
            "expires_at": "2026-06-04T18:00:00+00:00",
        },
    )

    with patch("trip_mcp.challenges.unauthed_client", return_value=fake):
        state = await challenges._ensure_challenge_resolved()

    assert state.redeemed is True
    assert state.mcp_token == "fake.jwt.token.string"

    # _pending cleared after successful redemption.
    assert challenges._pending is None


@pytest.mark.asyncio
async def test_pending_poll_returns_410_clears_pending_creates_new_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Branch 5: _pending + poll → 410 (expired/consumed) → clear
    _pending, then fall through to branch 1 (POST new /challenge).
    Single _ensure_challenge_resolved call handles the full
    fallback cycle."""
    from trip_mcp import challenges

    monkeypatch.setenv("TC_MCP_USER_EMAIL", "u@example.com")
    challenges._store_pending(
        code="stale-code-aaaaaaaaaa",
        magic_link_url="https://x.example/redeem?code=stale-code-aaaaaaaaaa",
    )

    # First call: poll returns 410. Second call: POST returns fresh code.
    poll_resp = MagicMock()
    poll_resp.status_code = 410
    poll_resp.json.return_value = {"detail": "expired"}

    post_resp = MagicMock()
    post_resp.status_code = 200
    post_resp.json.return_value = {
        "code": "fresh-code-bbbbbbbbbb",
        "poll_url": "https://backend.example.com/auth/mcp/poll/fresh-code-bbbbbbbbbb",
        "expires_at": "2026-06-04T18:00:00+00:00",
    }

    fake = MagicMock()
    fake.get = MagicMock(return_value=poll_resp)
    fake.post = MagicMock(return_value=post_resp)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]

    with patch("trip_mcp.challenges.unauthed_client", return_value=fake):
        state = await challenges._ensure_challenge_resolved()

    assert state.redeemed is False
    assert state.magic_link_url is not None
    assert "fresh-code-bbbbbbbbbb" in state.magic_link_url

    # Both calls happened in order: poll then post.
    fake.get.assert_called_once()
    fake.post.assert_called_once()

    # _pending now points at the fresh code.
    assert challenges._pending is not None
    assert challenges._pending.code == "fresh-code-bbbbbbbbbb"
