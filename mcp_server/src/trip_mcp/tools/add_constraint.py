"""add_constraint MCP tool — slice 3.4a commit 5.

Single backend call: POST /trips/{id}/constraints. Returns a
conversational "constraint added + re-audit running" message on 202,
or a failure message on any non-202.

Per slice 3.4a Q3 design: the underlying job IS a refine (not a new
JobKind). When we say "re-audit running" the LLM routes follow-up to
get_trip — same UX as refine_trip.

Description sync: agents/prompts.md §4.5.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import format_constraint_enqueued, format_constraint_failed

# Source: agents/prompts.md §4.5 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the new-constraint tool. When a user states a constraint they
want enforced across the whole trip — use this tool.** Do not store the
constraint conversationally from memory; this tool persists it to the
trip and re-audits the existing plan against it.

Required: trip_id and constraint_text (verbatim from the user).
Optional: constraint_kind — one of "budget", "dietary", "mobility",
"no_go", "walking_limit", "custom". Pick the closest fit; default
"custom" if uncertain.

Call this for instructions like:
- "actually we have a ₹3000/day cap" → constraint_kind="budget"
- "I just remembered, I'm vegetarian" → constraint_kind="dietary"
- "no nightclubs" → constraint_kind="no_go"
- "we can't walk more than 5km in a day" → constraint_kind="walking_limit"
- "we want to be home before midnight every night" → constraint_kind="custom"

DO NOT use this tool for one-off preferences scoped to a single day
("I don't want sushi tomorrow", "skip the museum on Day 2") — those
belong in regenerate_day with a hint.

DO NOT use this tool to RELAX a prior constraint ("never mind the
budget"). v1.0 only supports additive constraints. If the user asks
to remove a constraint, tell them this isn't supported yet and offer
to start a new trip via create_trip.

DO NOT call this tool for general travel advice — answer
conversationally or use web_search.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The re-audit runs in the background and takes about 10 minutes
  (same as refine_trip — the new constraint is merged with all prior
  constraints and the Auditor re-validates the entire plan).
- Tell the user the constraint was added and a re-audit is running.
  Offer to check back via get_trip.
- DO NOT claim the trip "now satisfies" the new constraint until
  get_trip confirms state=ready. The previous itinerary may still
  show blocks that violate the new constraint during the re-audit.
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
    except Exception:  # noqa: BLE001
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


async def add_constraint(
    *,
    trip_id: uuid.UUID,
    constraint_text: str,
    constraint_kind: str = "custom",
) -> str:
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    body = {"constraint_text": constraint_text, "constraint_kind": constraint_kind}

    with _http_client(token) as client:
        resp = client.post(f"/trips/{trip_id}/constraints", json=body)
        if resp.status_code != 202:
            return format_constraint_failed(trip_id=trip_id, reason=_extract_reason(resp))

    return format_constraint_enqueued(trip_id=trip_id, constraint_text=constraint_text)
