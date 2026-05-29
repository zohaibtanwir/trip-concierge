"""create_trip MCP tool — first authenticated tool in the server.

Two-call flow: POST /trips (creates the row, returns trip_id) →
POST /trips/{id}/plan (enqueues the crew job, returns 202). On the
happy path returns a conversational message naming the trip_id, the
share URL, and the ~10-minute expectation.

Input validation goes through trip_agents.schemas.CreateTripInput so
the Pydantic model is the single source of truth for both runtime
validation and the JSON Schema emitted to Claude Desktop (see
server.py).

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
from pydantic import ValidationError
from trip_agents.schemas import CreateTripInput

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    _share_url,
    format_clarification_needed,
    format_create_failed,
    format_created_trip,
    format_partial_failure,
)

# Source: agents/prompts.md §4.1 — keep in sync. Per
# .claude/rules/mcp-tool-description-style.md, prompts.md is canonical;
# edits to this string must update prompts.md in the same commit.
DESCRIPTION = """
**This is the trip planning tool. When a user asks to plan, build, design, or
create a trip — use this tool.** Do not use places_search, web_search, or
your general travel knowledge to construct a trip yourself. This tool
produces a real, persistent, multi-agent itinerary the user can save, refine,
and share. Built-in search returns ephemeral results that don't persist and
can't be refined.

Required: at least one of `destination` or `vibe`.
Recommended: dates, group_size, budget_total.

DO NOT call this tool if the user is asking about an existing trip — use
refine_trip or get_trip instead. If a trip_id has already been mentioned in
this conversation, the user almost certainly wants to modify it, not start over.

DO NOT call this tool for general travel questions ("what's the best time to
visit Japan?") — answer those conversationally without invoking the planner.
You may use web_search or your training knowledge for those.

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


# _share_url lifted to trip_mcp.tools._responses (slice 3.5) — single source
# of truth for the URL convention. Pre-3.5 the helper returned
# /trips/{id}; slice 3.5 changed it to /shared/{id} (unauth viewer
# endpoint). See _responses.py:_share_url docstring + the three
# URL pin tests in test_responses.py + test_share_trip.py.


def _missing_fields_from_validation_error(exc: ValidationError) -> list[str]:
    """Translate a Pydantic ValidationError into the user-facing missing-field
    list that format_clarification_needed knows how to render.

    Only one cross-field case today: "at least one of destination or vibe".
    Per-field required-failures could land here in future tools.
    """
    for err in exc.errors():
        msg = str(err.get("msg", ""))
        if "destination" in msg and "vibe" in msg:
            return ["destination_or_vibe"]
    # Fallback — list the field names that failed.
    return [str(err.get("loc", ["unknown"])[-1]) for err in exc.errors()]


async def create_trip(
    *,
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    group_size: int = 1,
    budget_total: float | None = None,
    currency: str = "USD",
    pace: str = "balanced",
    vibe: str | None = None,
) -> str:
    """Implementation. Returns a string for Claude Desktop to render.

    Why string-not-dict: MCP tool results render directly. JSON would
    force the LLM to re-summarize. Pre-summarized text is better UX.
    """
    try:
        validated = CreateTripInput(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            group_size=group_size,
            budget_total=budget_total,
            currency=currency,
            pace=pace,  # type: ignore[arg-type]
            vibe=vibe,
        )
    except ValidationError as exc:
        return format_clarification_needed(_missing_fields_from_validation_error(exc))

    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    # Translate CreateTripInput (MCP-boundary shape) → POST /trips body
    # (backend-boundary shape). Both projects own their own schemas; the
    # mapping happens here, at the seam.
    body: dict[str, Any] = {
        "destination": validated.destination or "",
        "group_size": validated.group_size,
        "currency": validated.currency,
        "pace": validated.pace,
        "constraints": {},
    }
    if validated.start_date is not None:
        body["start_date"] = validated.start_date
    if validated.end_date is not None:
        body["end_date"] = validated.end_date
    if validated.budget_total is not None:
        body["budget_total"] = str(validated.budget_total)

    with _http_client(token) as client:
        create_resp = client.post("/trips", json=body)
        if create_resp.status_code != 201:
            return format_create_failed(_extract_reason(create_resp))

        created = create_resp.json()
        trip_id = uuid.UUID(created["id"])
        share = _share_url(trip_id)

        plan_resp = client.post(f"/trips/{trip_id}/plan")
        if plan_resp.status_code != 202:
            return format_partial_failure(trip_id=trip_id, share_url=share)

    return format_created_trip(
        trip_id=trip_id,
        destination=validated.destination or validated.vibe or "your",
        budget_total=validated.budget_total,
        currency=validated.currency,
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
