"""create_trip MCP tool — first authenticated tool in the server.

Two-call flow: POST /trips (creates the row, returns trip_id) →
POST /trips/{id}/plan (enqueues the crew job, returns 202). On the
happy path returns a conversational message naming the trip_id, the
share URL, and the ~10-minute expectation.

Description sync: the tool description is sourced from
agents/prompts.md §4.1. Keep both in sync — see
.claude/rules/mcp-tool-description-style.md.

The test seam: `_token_file` and `_http_client` are module-level
indirections so tests can patch them without monkey-patching the
underlying httpx / auth code.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_create_failed,
    format_created_trip,
    format_partial_failure,
)

# Source: agents/prompts.md §4.1 — keep in sync. Per
# .claude/rules/mcp-tool-description-style.md, prompts.md is canonical;
# edits to this string must update prompts.md in the same commit.
DESCRIPTION = """
Use this tool when the user expresses intent to plan a new trip and provides at
least a destination or a vibe/style description. The tool creates a fresh trip
record and starts a multi-agent planning job in the background.

Required: at least one of `destination` or `vibe`.
Recommended: dates, group_size, budget_total.

DO NOT call this tool if the user is asking about an existing trip — use
refine_trip or get_trip instead. If a trip_id has already been mentioned in
this conversation, the user almost certainly wants to modify it, not start over.

DO NOT call this tool for general travel questions ("what's the best time to
visit Japan?") — answer those conversationally without invoking the planner.

Timing and what to say to the user:
- The tool call returns in under 1 second with a trip_id and a share URL.
- The full plan is NOT available immediately — the background job takes about
  10 minutes to finish. The share URL works right away but shows a planning
  state until the job completes.
- Tell the user the trip was created and offer to check back via get_trip.
- DO NOT promise the plan is "ready," "available now," or "done" — those are
  false until get_trip confirms it.
"""


def _token_file() -> Path:
    """Indirection so tests can patch the token-file path."""
    return default_token_file()


def _http_client(token: str) -> httpx.Client:
    """Indirection so tests can patch the httpx client construction."""
    return httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=30.0,
    )


def _share_url(trip_id: uuid.UUID) -> str:
    # The PWA at this path lands the user on the trip view. PRD §F1.
    return f"https://tripconcierge.app/trips/{trip_id}"


async def create_trip(
    *,
    destination: str,
    start_date: str | None = None,
    end_date: str | None = None,
    group_size: int = 1,
    budget_total: float | None = None,
    currency: str = "USD",
    pace: str = "balanced",
    vibe: str = "",
    constraints: dict[str, Any] | None = None,
) -> str:
    """Implementation. Returns a string for Claude Desktop to render.

    Why string-not-dict: MCP tool results render directly. JSON would
    force the LLM to re-summarize. Pre-summarized text is better UX.
    """
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    body: dict[str, Any] = {
        "destination": destination,
        "group_size": group_size,
        "currency": currency,
        "pace": pace,
        "constraints": constraints or {},
    }
    if start_date is not None:
        body["start_date"] = start_date
    if end_date is not None:
        body["end_date"] = end_date
    if budget_total is not None:
        body["budget_total"] = str(budget_total)
    # `vibe` is documented as a tool input but doesn't have a column on the
    # Trip row in v1.0 — it's a future PRD §F4 structured-constraint. Drop
    # silently rather than 422 the user.
    _ = vibe

    with _http_client(token) as client:
        create_resp = client.post("/trips", json=body)
        if create_resp.status_code != 201:
            # Never raise — every failure surfaces as a tool-level message
            # the LLM can render to the user.
            return format_create_failed(_extract_reason(create_resp))

        created = create_resp.json()
        trip_id = uuid.UUID(created["id"])
        share = _share_url(trip_id)

        plan_resp = client.post(f"/trips/{trip_id}/plan")
        if plan_resp.status_code != 202:
            return format_partial_failure(trip_id=trip_id, share_url=share)

    return format_created_trip(
        trip_id=trip_id,
        destination=destination,
        budget_total=budget_total,
        currency=currency,
        share_url=share,
    )


def _extract_reason(resp: Any) -> str:
    """Pull a one-line failure reason from a FastAPI error response.

    Best-effort. Falls back to the status code if the body doesn't match
    FastAPI's standard shape.
    """
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
            field = first.get("loc", [None])[-1]
            msg = first.get("msg", "validation failed")
            return f"{field}: {msg}" if field else msg
    return f"HTTP {resp.status_code}"
