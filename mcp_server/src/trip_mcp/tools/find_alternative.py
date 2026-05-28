"""find_alternative MCP tool — slice 3.4a commit 5.

Single backend call: POST /trips/{id}/blocks/{block_id}/alternative.
Unlike refine_trip / regenerate_day / add_constraint (which enqueue
arq jobs and return 202), this tool runs SYNCHRONOUSLY — the backend
runs the Researcher crew inside the request thread under a 90s
asyncio.wait_for ceiling, and the 3 alternatives come back inline.

Branch logic is load-bearing here. The backend returns:
- 200 + AlternativesList → render 3 ranked alternatives.
- 409 + kind="active_job" → distinct UX from "not_ready".
- 409 + kind="not_ready" + state → branch on state value.
- 404 → could be trip-not-found OR block-not-found. We distinguish
  via the detail string ("block not found on this trip" vs
  "trip not found") because both are 404.
- 504 + kind="timeout" + elapsed_seconds → honest timeout report.
- Anything else → catch-all "failed" with the reason surfaced.

httpx client timeout is 100s (10s slack over the backend's 90s
asyncio ceiling) so we don't time out before the backend does and
swallow the structured 504 body.

Description sync: agents/prompts.md §4.7.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_alternative_active_job,
    format_alternative_block_not_found,
    format_alternative_failed,
    format_alternative_not_ready,
    format_alternative_succeeded,
    format_alternative_timeout,
    format_trip_not_found,
)

# Source: agents/prompts.md §4.7 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the single-block swap tool. When a user wants to replace
exactly ONE block in an existing trip — use this tool.** Do not use
regenerate_day (that replaces the whole day, which is more disruptive
and slower). Do not invent alternatives conversationally; this tool
returns 3 real venues researched with search, each with a source URL.

Required: trip_id and block_id. block_id MUST be a real UUID from the
trip's data — get it from get_trip; DO NOT synthesize a UUID-shaped
string from context. If you don't have a block_id, call get_trip first.

Optional: reason — short free-text explaining why the user wants to
swap this block (e.g., "closed for renovations", "too expensive",
"bad reviews"). Helps the ranking but is not required.

Call this for instructions like:
- "this restaurant is closed, suggest something else"
- "I don't want to do the museum, what else is there?"
- "give me three other options for Day 2 dinner"
- "swap the 7pm spot for something quieter"

DO NOT use this for replanning a whole day — use regenerate_day.
DO NOT use this for replanning the whole trip — use refine_trip.
DO NOT use this for hypothetical "what if" questions — answer
conversationally.

DO NOT call this tool if the trip isn't ready yet. The tool will
refuse with a clarification message if you call it on a trip whose
initial planning isn't complete (state ∈ {queued, running, failed,
cancelled, never_planned}). Call get_trip first if unsure.

Timing and what to say to the user:
- This tool runs SYNCHRONOUSLY and takes up to 90 seconds. Set the
  user's expectation: "Let me look up alternatives — this takes about
  a minute."
- The response is exactly 3 ranked alternatives with source URLs and
  one-line rationales. Present all 3 (best first) and ask the user
  to pick one.
- After the user picks, follow up with refine_trip describing the
  chosen swap. find_alternative itself does NOT persist the swap.
- DO NOT claim a venue is the "best" or "perfect" alternative — present
  the ranking and let the user choose.
- If the tool returns a timeout message, DO NOT retry automatically.
  Tell the user it timed out and ask whether to try again. (Each
  retry costs ~$0.30 in background LLM spend even on timeout.)
"""

# httpx client timeout: 10s slack over the backend's 90s asyncio.wait_for
# ceiling. If httpx timed out first we'd surface a generic connection
# error instead of the backend's structured kind="timeout" body.
_HTTP_TIMEOUT_SECONDS = 100.0


def _token_file() -> Path:
    return default_token_file()


def _http_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=_HTTP_TIMEOUT_SECONDS,
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


async def find_alternative(
    *,
    trip_id: uuid.UUID,
    block_id: uuid.UUID,
    reason: str | None = None,
) -> str:
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    body: dict[str, Any] = {}
    if reason is not None:
        body["reason"] = reason

    with _http_client(token) as client:
        resp = client.post(f"/trips/{trip_id}/blocks/{block_id}/alternative", json=body)

    # Happy path.
    if resp.status_code == 200:
        payload = resp.json()
        alternatives = payload.get("alternatives") or []
        # block_venue_name isn't available without an extra get_trip call;
        # keep wording generic. Tests assert "Original Restaurant" only
        # when it's passed explicitly, which the live MCP flow doesn't.
        return format_alternative_succeeded(
            alternatives=alternatives,
            block_venue_name="that block",
        )

    # 409 — branch on kind.
    if resp.status_code == 409:
        body_json = _safe_json(resp)
        kind = body_json.get("kind") if isinstance(body_json, dict) else None
        if kind == "active_job":
            return format_alternative_active_job(
                active_job_kind=str(body_json.get("active_job_kind", "")),
                active_job_id=str(body_json.get("active_job_id", "")),
            )
        if kind == "not_ready":
            return format_alternative_not_ready(str(body_json.get("state", "unknown")))
        # Unknown kind — fall through to generic failure rather than
        # silently picking the wrong branch.
        return format_alternative_failed(trip_id=trip_id, reason=_extract_reason(resp))

    # 404 — distinguish trip-not-found from block-not-found via the detail
    # string (both are 404, no `kind` body field on this path).
    if resp.status_code == 404:
        detail = _extract_reason(resp).lower()
        if "block" in detail:
            return format_alternative_block_not_found(trip_id=trip_id, block_id=block_id)
        return format_trip_not_found(trip_id)

    # 504 — timeout with structured body.
    if resp.status_code == 504:
        body_json = _safe_json(resp)
        elapsed = 90.0
        if isinstance(body_json, dict):
            raw_elapsed = body_json.get("elapsed_seconds")
            if isinstance(raw_elapsed, (int, float)):
                elapsed = float(raw_elapsed)
        return format_alternative_timeout(elapsed_seconds=elapsed)

    # Catch-all.
    return format_alternative_failed(trip_id=trip_id, reason=_extract_reason(resp))


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None
