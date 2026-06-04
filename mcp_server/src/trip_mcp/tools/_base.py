"""@requires_auth decorator — the seam between MCP tools and the token.

Every tool calls into the backend via http_client.authed_client(), which
needs a token from disk. If the token isn't there, we don't want the LLM
to see a raw exception — we want a clear instruction for the human on
how to fix it.

Slice 3.1 returned a dev-CLI hint string when no token was on disk.
Slice 4.1b (0h0) swaps that for the production magic-link challenge
flow: the decorator drives `_ensure_challenge_resolved` from challenges.py,
which either returns a "redeemed" state (save the JWT + retry the inner
tool function) or a sign-in URL the user clicks.

Usage:

    @requires_auth()
    async def create_trip(token: str, ...) -> ...:
        # token is the JWT string; tools call authed_client() themselves
        ...

The decorator passes the resolved token as the first arg. Tools that
don't need the token can skip the decorator (none yet exist).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import TypeVar

from trip_mcp.auth import NoTokenError, load_token, save_token
from trip_mcp.challenges import _ensure_challenge_resolved, _format_challenge_message

T = TypeVar("T")


def requires_auth(
    *, token_file: Path | None = None
) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Wrap an async tool function.

    On NoTokenError, drives the magic-link challenge flow:
    - If the flow returns redeemed=True, save the JWT and retry the inner
      tool function with the now-stored token (single-call cold-start).
    - Otherwise, return the formatted challenge message (URL + retry hint,
      OR "set TC_MCP_USER_EMAIL" hint) as the tool's text so Claude
      Desktop surfaces it directly to the user.
    """

    def decorator(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> str:
            try:
                token = load_token(token_file=token_file)
            except NoTokenError:
                state = await _ensure_challenge_resolved()
                if state.redeemed and state.mcp_token is not None:
                    save_token(state.mcp_token, token_file=token_file)
                    token = load_token(token_file=token_file)
                    return await fn(token, *args, **kwargs)
                return _format_challenge_message(state)
            return await fn(token, *args, **kwargs)

        return wrapper

    return decorator
