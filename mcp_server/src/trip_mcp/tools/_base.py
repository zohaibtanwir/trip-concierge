"""@requires_auth decorator — the seam between MCP tools and the token.

Every tool calls into the backend via http_client.authed_client(), which
needs a token from disk. If the token isn't there, we don't want the
LLM to see a raw exception — we want a clear instruction for the human
on how to fix it.

In slice 3.1 the fix is the dev CLI. Slice 4.1 swaps the message body
to the clicked-link flow without touching tool source — the decorator
is the only place that knows.

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

from trip_mcp.auth import NoTokenError, load_token

T = TypeVar("T")

_DEV_CLI_HINT = (
    "Not authenticated. To use Trip Concierge MCP tools, issue a dev token:\n"
    "\n"
    "    uv run --project backend tc-issue-mcp-token --email <your-email>\n"
    "\n"
    "Then save the printed token to ~/.config/trip-concierge/token (mode 0600) "
    "and restart Claude Desktop.\n"
    "\n"
    "Note: this dev CLI is temporary. The production magic-link flow lands in "
    "Trip Concierge slice 4.1."
)


def requires_auth(
    *, token_file: Path | None = None
) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    """Wrap an async tool function. On NoTokenError, return the CLI hint
    as the tool's result so Claude Desktop surfaces it directly to the user.
    """

    def decorator(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> str:
            try:
                token = load_token(token_file=token_file)
            except NoTokenError:
                return _DEV_CLI_HINT
            return await fn(token, *args, **kwargs)

        return wrapper

    return decorator
