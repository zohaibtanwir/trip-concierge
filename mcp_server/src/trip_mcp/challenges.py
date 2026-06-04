"""Pending-challenge module state for MCP magic-link auth — slice 4.1b (0h0).

ONE pending challenge per MCP server process. The stdio MCP architecture
is single-connection per Claude Desktop instance, so a module-level dict
is safe. If we ever move to a long-running daemon model that serves
multiple Claude Desktop instances, per-connection scoping becomes
necessary — file as v2.0 followup.

State machine driven by `_ensure_challenge_resolved`:
- No _pending + TC_MCP_USER_EMAIL set → POST /auth/mcp/challenge, store
  in _pending, return ChallengeState with magic_link_url.
- No _pending + TC_MCP_USER_EMAIL missing → return ChallengeState
  with magic_link_url=None (decorator surfaces the env-var hint).
- _pending + poll returns status=pending → return same magic_link_url,
  no second POST (waiting for user click).
- _pending + poll returns status=redeemed → return
  ChallengeState(redeemed=True, mcp_token=jwt), clear _pending.
- _pending + poll returns 410 (expired/consumed) → clear _pending,
  fall through to "no _pending" logic in the same call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trip_mcp.auth import load_token, save_token
from trip_mcp.config import backend_url, user_email
from trip_mcp.http_client import unauthed_client


@dataclass
class ChallengeState:
    """Returned by `_ensure_challenge_resolved`. Three terminal shapes:

    - redeemed=True + mcp_token set → decorator calls save_token + retries
    - redeemed=False + magic_link_url set → decorator renders sign-in URL
    - redeemed=False + magic_link_url=None → decorator renders env-var hint
    """

    redeemed: bool = False
    magic_link_url: str | None = None
    mcp_token: str | None = None


@dataclass
class _Pending:
    code: str
    magic_link_url: str


# Module-level state — safe under the stdio single-connection assumption
# documented at the top of this file. Cleared via _clear_pending() (tests +
# the 410-fallthrough branch).
_pending: _Pending | None = None


def _store_pending(*, code: str, magic_link_url: str) -> None:
    global _pending
    _pending = _Pending(code=code, magic_link_url=magic_link_url)


def _clear_pending() -> None:
    """Reset the in-flight challenge state. Called when:
    - Backend reports the code is expired/consumed (start fresh).
    - The challenge is successfully redeemed (one-shot delivery).
    - Tests reset between cases (autouse fixture).
    """
    global _pending
    _pending = None


def _magic_link_url_for(code: str) -> str:
    """Mirror the backend's /redeem URL shape so we don't need the backend
    to include the URL in its /challenge response.
    """
    return f"{backend_url()}/auth/mcp/redeem?code={code}"


async def _ensure_challenge_resolved() -> ChallengeState:
    """Drive the per-tool-call challenge state machine.

    Called by @requires_auth on NoTokenError. Returns ChallengeState
    indicating what the decorator should do next: save+retry, render URL,
    or render env-var hint.
    """
    global _pending

    if _pending is not None:
        # Poll the existing code's status.
        with unauthed_client() as client:
            response = client.get(f"/auth/mcp/poll/{_pending.code}")

        if response.status_code == 200:
            body = response.json()
            if body.get("status") == "redeemed":
                token = body.get("mcp_token")
                _clear_pending()
                return ChallengeState(redeemed=True, mcp_token=token)
            # status=pending or any other non-terminal — keep waiting.
            return ChallengeState(magic_link_url=_pending.magic_link_url)

        if response.status_code == 410:
            # Expired or consumed — clear and create a fresh challenge
            # in the same call (don't make the user issue a second tool
            # call just to advance the state machine).
            _clear_pending()
        else:
            # Unexpected status — fail open by clearing and re-trying.
            # Avoids getting stuck on a stale _pending state.
            _clear_pending()

    # No _pending (or just cleared). Check whether we can create a new one.
    email = user_email()
    if email is None:
        return ChallengeState(magic_link_url=None)

    with unauthed_client() as client:
        response = client.post("/auth/mcp/challenge", json={"email": email})

    if response.status_code != 200:
        # Backend reachable but errored. Surface a no-URL state so the
        # decorator renders the env-var hint (best fallback message we
        # have without more error-class plumbing).
        return ChallengeState(magic_link_url=None)

    body = response.json()
    code = body["code"]
    magic_link_url = _magic_link_url_for(code)
    _store_pending(code=code, magic_link_url=magic_link_url)
    return ChallengeState(magic_link_url=magic_link_url)


async def resolve_token_or_format_message(
    *, token_file: Path | None = None
) -> tuple[str | None, str | None]:
    """Helper for tools that catch NoTokenError directly (rather than via
    the @requires_auth decorator).

    Drives the challenge flow and returns (token, message). Exactly one
    is non-None:
    - (token, None)   → tool can proceed with `token`
    - (None, message) → tool returns `message` to the user as its result

    Lets each tool stay a single `async def` while still participating in
    the magic-link flow. The 10 tools in tools/ all use this helper.
    """
    state = await _ensure_challenge_resolved()
    if state.redeemed and state.mcp_token is not None:
        save_token(state.mcp_token, token_file=token_file)
        return load_token(token_file=token_file), None
    return None, _format_challenge_message(state)


def _format_challenge_message(state: ChallengeState) -> str:
    """Convert a ChallengeState into the text the LLM surfaces to the user.

    Two variants:
    - magic_link_url=None → "set TC_MCP_USER_EMAIL" hint
    - magic_link_url set → sign-in URL + "let me know" retry hint
    """
    if state.magic_link_url is None:
        return (
            "Trip Concierge MCP is not yet configured for your account.\n\n"
            "Set `TC_MCP_USER_EMAIL` in your Claude Desktop MCP config to "
            "your email, restart Claude Desktop, and try again.\n\n"
            "Example config snippet:\n"
            '  "trip-concierge": {\n'
            '    "command": "tc-mcp-server",\n'
            '    "env": { "TC_MCP_USER_EMAIL": "you@example.com" }\n'
            "  }"
        )
    return (
        "Sign in to Trip Concierge to use this tool:\n\n"
        f"    {state.magic_link_url}\n\n"
        "After signing in (it takes about 10 seconds), let me know and "
        "I'll retry your request."
    )
