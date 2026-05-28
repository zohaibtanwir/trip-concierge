"""regenerate_day MCP tool — slice 3.3 commit 5.

Two HTTP calls per invocation:
  1. GET /trips/{id}/plan/status — gate-check (refuse on non-done state)
  2. POST /trips/{id}/days/{n}/regenerate — enqueue (only if done)

The pre-call gate is the load-bearing UX: surfaces "trip not ready" before
any backend enqueue work. Slice 3.3 commit 4 design Q3 = option (a) for
the refusal semantics.

Description sync: agents/prompts.md §4.4.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_regenerate_day_not_ready,
    format_regenerate_enqueued,
    format_regenerate_failed,
)

DESCRIPTION = """
**This is the single-day replan tool. When a user wants to redo one
specific day of an existing trip — use this tool.** Do not use refine_trip
(that re-plans the whole trip and costs more LLM time). Do not edit the day
conversationally; this tool persists a new set of blocks for the target day
while preserving any blocks the user has locked.

Required: trip_id and day_number (1-indexed).
Recommended: hint (free-text — what kind of change the user wants).

Call this for instructions like:
- "redo Day 2"
- "change the second day completely"
- "Day 3 isn't working, give me something different"
- "regenerate Day 4 with more food and less hiking"

DO NOT call this tool if the user wants changes spanning multiple days —
use refine_trip instead.

DO NOT call this tool if the user wants to swap just one venue — that's
narrower than a day regeneration. Ask the user if they meant one specific
block or the whole day.

DO NOT call this tool for general travel questions — answer conversationally
or use web_search.

DO NOT call this tool if the trip's state is "planning" or "failed" — call
get_trip first to see what state it's in. The tool will refuse with a
clarification message if you call it on a trip that's not "ready" yet.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The day regeneration runs in the background and takes about 3-5 minutes
  (faster than refine_trip because the scope is one day, not the whole trip).
- Locked blocks at specific positions are preserved automatically — the
  user does not need to mention them.
- Tell the user the day regeneration was started and offer to check back
  via get_trip.
- DO NOT claim the new day is "ready," "done," or "applied" until get_trip
  confirms state=ready.
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
    try:
        body = resp.json()
    except Exception:
        return f"HTTP {resp.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    return f"HTTP {resp.status_code}"


async def regenerate_day(*, trip_id: uuid.UUID, day_number: int, hint: str | None = None) -> str:
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    with _http_client(token) as client:
        # Gate: check trip state before enqueueing.
        status_resp = client.get(f"/trips/{trip_id}/plan/status")
        if status_resp.status_code != 200:
            return format_regenerate_failed(
                trip_id=trip_id,
                reason=f"couldn't read trip status (HTTP {status_resp.status_code})",
            )
        state = status_resp.json().get("state")
        if state != "done":
            return format_regenerate_day_not_ready(str(state))

        # Trip is ready — enqueue.
        body: dict[str, Any] = {}
        if hint is not None:
            body["hint"] = hint
        post_resp = client.post(f"/trips/{trip_id}/days/{day_number}/regenerate", json=body)
        if post_resp.status_code != 202:
            return format_regenerate_failed(trip_id=trip_id, reason=_extract_reason(post_resp))

    return format_regenerate_enqueued(trip_id=trip_id, day_number=day_number, destination="your")
