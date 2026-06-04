"""refine_trip MCP tool — slice 3.3 commit 5.

Single backend call: POST /trips/{id}/refine. Returns a conversational
"enqueued, check via get_trip" message; surfaces 404/409/etc. as
failure messages.

Description sync: agents/prompts.md §4.3.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import format_refine_enqueued, format_refine_failed

DESCRIPTION = """
**This is the trip modification tool. When a user wants to change something
about an existing trip — use this tool.** Do not use create_trip (that
starts a new trip from scratch). Do not modify the trip conversationally
from memory; this tool persists the change to the database via a
multi-agent refinement process that respects budget and constraints.

Required: trip_id and refinement_description (free-text user instruction).

Call this for instructions like:
- "make Day 2 chiller"
- "swap that museum for something outdoor"
- "we're vegetarian, redo the food picks"
- "I want to spend less on Day 3"
- "redo the whole trip with a more relaxed pace"

DO NOT call this tool if the user wants a different destination — that's a
new trip. Use create_trip instead. (Refining to "redo from scratch but same
destination" is fine.)

DO NOT call this tool for very narrow edits like "regenerate just Day 2" —
use regenerate_day instead, which is faster and cheaper.

DO NOT call this tool for general travel questions — answer conversationally
or use web_search.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The refinement runs in the background and takes about 10 minutes. Locked
  blocks are preserved automatically; the rest of the plan is updated under
  the trip's existing constraints.
- Tell the user the refinement was started and offer to check back via
  get_trip.
- DO NOT claim the refinement is "applied," "done," or "ready" until
  get_trip confirms state=ready. The previous itinerary may still be visible
  during planning.
"""


def _token_file() -> Path:
    return default_token_file()


def _http_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=30.0,
    )


def _extract_reason(resp: Any) -> str:
    """Pull a one-line failure reason from a FastAPI error response."""
    try:
        body = resp.json()
    except Exception:
        return f"HTTP {resp.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict):
            msg = first.get("msg", "validation failed")
            return str(msg)
    return f"HTTP {resp.status_code}"


async def refine_trip(*, trip_id: uuid.UUID, refinement_description: str) -> str:
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

    body = {"refinement_description": refinement_description}
    destination = "your"  # we don't have it without an extra GET; keep generic

    with _http_client(token) as client:
        resp = client.post(f"/trips/{trip_id}/refine", json=body)
        if resp.status_code != 202:
            return format_refine_failed(trip_id=trip_id, reason=_extract_reason(resp))

    return format_refine_enqueued(trip_id=trip_id, destination=destination)
