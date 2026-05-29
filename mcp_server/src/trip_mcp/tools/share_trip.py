"""share_trip MCP tool — pure URL construction, no backend call.

Slice 3.5 commit 3. Structurally novel in the corpus: no httpx
client, no backend round-trip, no /plan/status pre-check.

The LLM, per §4.10, calls get_trip first if unsure of trip state,
then passes the state value to share_trip. The tool routes:
  state in {None, "done", "succeeded"} → format_share_succeeded
  otherwise                              → format_share_not_ready(state)

NoTokenError still gates the path because the slice-3.3 token
discipline applies uniformly across all MCP tools — the absence
of an installed token surfaces the dev-CLI hint regardless of
whether the tool calls the backend.

Description sync: agents/prompts.md §4.10.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import default_token_file
from trip_mcp.tools._responses import (
    _share_url,
    format_share_not_ready,
    format_share_succeeded,
)

# Source: agents/prompts.md §4.10 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the share-link tool. When the user wants to share their trip
with someone else, or open it in the visual web app — use this tool.**
Do not paste the URL into the conversation from memory; this tool
returns the canonical share URL the backend knows about.

Required: trip_id.
Optional: state — the trip state from a recent get_trip call.

Returns a URL the user can copy. Anyone with the URL can view the
trip (read-only) — there's no separate sign-in or invite step.
v1.0a does NOT support revoking the URL after sharing; trip data
should not be considered private (treat the URL like an unlisted
YouTube video — security through obscurity at 128 bits, but anyone
with the link can see it).

Call this for instructions like:
- "share this trip with my partner"
- "send this to my friend"
- "give me a link I can text"
- "I want to see this in the web app"

DO NOT use this for printable/offline formats — use export_trip
instead (Markdown is portable; PDF is planned for v1.0b).

DO NOT use this if the trip isn't ready yet. The tool will return
a clarification message if the state value is in
{queued, running, failed, cancelled, never_planned}. If you're
unsure of state, call get_trip first and pass state=<the value
you read> into this tool.

DO NOT promise revocation. If the user asks "can I delete the link
later?", tell them honestly: not yet (v1.0a). They can delete the
trip entirely, which makes the link 404, but there's no per-link
revocation.

Timing and what to say to the user:
- The tool returns in under 100ms (no backend call — pure URL
  construction).
- Present the URL on its own line so Claude Desktop renders it as
  a clickable link.
- If the user asks how the recipient signs in — tell them they
  don't need to. The link works for anyone.
"""


def _token_file() -> Path:
    return default_token_file()


async def share_trip(
    *,
    trip_id: uuid.UUID,
    state: str | None = None,
    destination: str | None = None,
) -> str:
    """Pure transform: (trip_id, state?, destination?) → response string.
    No backend call.

    NoTokenError is gated for corpus consistency with the other tools
    (slice 3.3 discipline) — the absence of a token surfaces the dev
    CLI hint even though no backend call would happen.

    `destination` is an LLM-orchestrator hand-off from a prior turn
    (get_trip / create_trip). When the LLM has it, the share message
    names the real destination; when None, the formatter falls back to
    a generic message.
    """
    try:
        load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    # State-aware branching.
    if state is not None and state not in ("done", "succeeded"):
        return format_share_not_ready(state)

    return format_share_succeeded(
        trip_id=trip_id,
        destination=destination,
        share_url=_share_url(trip_id),
    )
