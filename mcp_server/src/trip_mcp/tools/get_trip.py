"""get_trip MCP tool — slice 3.3 commit 5.

Composes two backend reads (GET /trips/{id}/full + GET /plan/status) into
a single conversational response branching on state. The §4.2 prohibition
language tells the LLM exactly how to handle the failed-state response;
this tool is the surface that makes that prohibition meaningful.

Description sync: agents/prompts.md §4.2.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_trip_failed,
    format_trip_not_found,
    format_trip_planning,
    format_trip_succeeded,
)

# Source: agents/prompts.md §4.2 — keep in sync. Per
# .claude/rules/mcp-tool-description-style.md, prompts.md is canonical.
DESCRIPTION = """
**This is the trip retrieval tool. When a user asks about their trip's
status, contents, or what got planned — use this tool.** Do not summarize
from your conversation memory, do not use web_search to look up venues, do
not invent details. This tool returns the authoritative state of the trip
from the database. Built-in alternatives produce stale or fabricated data.

Required: trip_id (UUID). Returned by create_trip and persists across
sessions.

Call this when the user references "my trip", "the Goa trip", "what did we
plan", "is my trip ready", or any question about an existing trip. If a
trip_id has been mentioned earlier in the conversation, use it; if multiple
trip_ids are in play, ask which one.

DO NOT call this tool if the user is asking about a hypothetical trip they
haven't created yet — use create_trip instead.

DO NOT call this tool for general travel questions ("what's the best time to
visit Japan?") — answer those conversationally without invoking the planner.

**Honest reporting of trip state — this tool's most important behavior:**

- The response carries a `state` field with one of: planning, ready, failed.
- When state is "planning": the trip is being generated. Tell the user it's
  in progress; offer to check again in a few minutes. Include the
  progress_message if available.
- When state is "ready": the days array contains the full itinerary.
  Summarize day-by-day from THAT data; do not embellish.
- When state is "failed": the trip's planning did not complete successfully.
  Report this honestly with the response's error message. Suggest next
  steps (try create_trip again, or refine_trip if there's partial output
  worth keeping).

DO NOT claim the trip is "ready," "done," or "available" when state is
"failed" or "cancelled" — the days/blocks shown may be empty or stale.

DO NOT fabricate venues, times, or costs to fill gaps in the response. If a
Day has zero Blocks, say so plainly — that's the signal the user needs to
understand what went wrong.

DO NOT translate "failed" into softer language ("not quite finished",
"still working on it", "almost there"). The state is final; if planning
failed, the user needs to know so they can act.

The tool returns in under 1 second. There is no background work — what you
see IS the authoritative current state.
"""


def _token_file() -> Path:
    return default_token_file()


def _http_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=30.0,
    )


def _progress_summary(progress_message: Any) -> str | None:
    """Flatten the ProgressUpdate dict (agent + pass + message) into a
    one-line string for the planning response. Returns None if absent."""
    if not progress_message or not isinstance(progress_message, dict):
        return None
    agent = progress_message.get("agent", "")
    pass_num = progress_message.get("pass", "")
    msg = progress_message.get("message", "")
    if not agent:
        return None
    return f"{agent} (pass {pass_num}): {msg}" if msg else f"{agent} (pass {pass_num})"


async def get_trip(*, trip_id: uuid.UUID) -> str:
    """Retrieve and conversationally render a trip's current state.

    Two HTTP calls: /full for content, /plan/status for lifecycle. State-
    branched response per §4.2 description.
    """
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.challenges import (  # noqa: PLC0415
            resolve_token_or_format_message,
        )

        new_token, message = await resolve_token_or_format_message(token_file=_token_file())
        if new_token is None:
            assert message is not None
            return message
        token = new_token

    with _http_client(token) as client:
        full_resp = client.get(f"/trips/{trip_id}/full")
        if full_resp.status_code == 404:
            return format_trip_not_found(trip_id)
        if full_resp.status_code != 200:
            return format_trip_failed(
                trip_id=trip_id,
                destination="your",
                error=f"HTTP {full_resp.status_code}",
            )
        full_trip = full_resp.json()

        status_resp = client.get(f"/trips/{trip_id}/plan/status")

    destination = str(full_trip.get("destination") or "your")
    if status_resp.status_code == 404:
        # No JobRun, no active job — trip exists but never planned.
        return format_trip_failed(
            trip_id=trip_id,
            destination=destination,
            error="planning never started for this trip",
        )
    if status_resp.status_code != 200:
        return format_trip_failed(
            trip_id=trip_id,
            destination=destination,
            error=f"status endpoint HTTP {status_resp.status_code}",
        )

    status = status_resp.json()
    state = status.get("state")

    if state in ("queued", "running", "cancelling"):
        return format_trip_planning(
            trip_id=trip_id,
            destination=destination,
            progress_message=_progress_summary(status.get("progress_message")),
        )
    if state == "done":
        approved = status.get("approved")
        if approved is False:
            # Crew completed but auditor refused — surface as failed UX.
            return format_trip_failed(
                trip_id=trip_id,
                destination=destination,
                error="the planner could not satisfy all your constraints",
            )
        return format_trip_succeeded(full_trip)
    # failed | cancelled | anything else — treat as failed for UX.
    return format_trip_failed(
        trip_id=trip_id,
        destination=destination,
        error=status.get("error"),
    )
