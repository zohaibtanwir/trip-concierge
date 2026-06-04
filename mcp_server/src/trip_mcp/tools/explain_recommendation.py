"""explain_recommendation MCP tool — slice 3.4b commit 4.

Single backend call: GET /trips/{id}/explain/{block_id}. Pure-read
tool — no body, no fetch, no LLM. The backend returns a structured
body whose `rationale` field is either a non-empty string or `null`
(JSON null) per the slice-3.4b commit 3 gap-surfacing contract.

Branch logic:
  200 + rationale (str)  → format_explain_with_rationale
  200 + rationale (null) → format_explain_with_gap (literal qek text)
  404 "trip"             → format_trip_not_found
  404 "block"            → format_explain_block_not_found
  other                  → format_alternative_failed reused (catch-all
                           that names the failure honestly)

The 404 detail-string-parse mirrors slice 3.4a's alternative tool;
ticket trip-concierge-or8 will convert both backend routes to
JSONResponse + kind in one pass.

Description sync: agents/prompts.md §4.8.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_alternative_failed,
    format_explain_block_not_found,
    format_explain_with_gap,
    format_explain_with_rationale,
    format_trip_not_found,
)

# Source: agents/prompts.md §4.8 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the why-this-venue tool. When a user asks why a specific block
is in their trip — call this tool.** Do not synthesize an answer
conversationally from the venue name; this tool returns the actual
stored rationale + source URLs the Researcher used, so the user can
verify the recommendation themselves.

Required: trip_id and block_id. block_id MUST be a real UUID from
get_trip — DO NOT synthesize one from context. (Same prohibition as
find_alternative; layered defense.)

Call this for instructions like:
- "why this restaurant?"
- "what's the source for the Day 2 museum?"
- "where did this recommendation come from?"
- "is this place actually good?" (the user wants the evidence)

Call this proactively when the user seems skeptical of a specific
recommendation, even if they don't explicitly ask "why". Surfacing
sources is the trust-building move.

DO NOT use this for general venue questions ("is sushi popular in
Tokyo?") — that's a web_search question, not a stored-rationale
question.

DO NOT use this for explanations of the trip as a whole — there's
no per-trip rationale, only per-block. If the user asks "why this
whole trip?", point them at individual blocks they want to dig into.

CRITICAL — gap-surfacing discipline:

The backend returns the rationale as JSON null when no rationale was
captured for this block — usually because the crew's step_callback
didn't fire during planning (tracking ticket trip-concierge-qek).
The tool surfaces this honestly with text like "The Researcher's
per-block rationale wasn't captured for this venue — here are the
sources it used."

When you see that gap message, DO NOT synthesize a plausible rationale
from the venue name. Tell the user honestly. The user trusts the
product more when we name the gap than when we paper over it.

Same discipline as get_trip's "failed" state messaging from slice 3.3:
honest broken beats invisible broken.

Timing and what to say to the user:
- The tool returns in under 1 second (pure DB read; no LLM call).
- Present the rationale (or the gap message), then list the sources.
- If a source URL matches a research item the user added via
  add_source, surface that provenance: "this came from your Reddit
  thread."
"""


def _token_file() -> Path:
    return default_token_file()


def _http_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=15.0,
    )


def _extract_reason(resp: Any) -> str:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    return f"HTTP {resp.status_code}"


async def explain_recommendation(*, trip_id: uuid.UUID, block_id: uuid.UUID) -> str:
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
        resp = client.get(f"/trips/{trip_id}/explain/{block_id}")

    # 200 — gap-vs-rationale branch on body.rationale.
    if resp.status_code == 200:
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = {}
        venue_name = str(payload.get("venue_name", "this block"))
        block_type = str(payload.get("block_type", "?"))
        sources = list(payload.get("sources") or [])
        user_source_matches = list(payload.get("user_source_matches") or [])
        rationale = payload.get("rationale")

        if isinstance(rationale, str) and rationale.strip():
            return format_explain_with_rationale(
                venue_name=venue_name,
                block_type=block_type,
                rationale=rationale,
                sources=sources,
                user_source_matches=user_source_matches,
            )
        # rationale is None or empty → gap path.
        return format_explain_with_gap(
            venue_name=venue_name,
            block_type=block_type,
            sources=sources,
            user_source_matches=user_source_matches,
        )

    # 404 — parse detail for trip-vs-block distinction (ticket or8).
    if resp.status_code == 404:
        detail = _extract_reason(resp).lower()
        if "block" in detail:
            return format_explain_block_not_found(trip_id=trip_id, block_id=block_id)
        return format_trip_not_found(trip_id)

    # Catch-all — name the failure honestly using the slice-3.4a
    # alternative_failed cadence so the LLM gets consistent UX.
    return format_alternative_failed(trip_id=trip_id, reason=_extract_reason(resp))
