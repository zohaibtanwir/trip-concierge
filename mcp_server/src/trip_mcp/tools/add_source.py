"""add_source MCP tool — slice 3.4b commit 4.

Single backend call: POST /trips/{id}/sources with either {url} or
{text}. Branches on the response body's `kind` field to route to
the right formatter — same pattern as find_alternative (slice 3.4a)
but with more failure modes because the 6-defense source_ingestion
stack surfaces four distinct exception classes through the route.

Branch table:
  200                                  → format_source_attached
  400  + kind="denied_host"            → format_source_denied_host
  404                                  → format_trip_not_found (slice 3.3 reuse)
  409  + kind="active_job"             → format_source_active_job
  413  + kind="too_large"              → format_source_too_large
  415  + kind="unsupported_content_type" → format_source_unsupported_content_type
  502  + kind="fetch_failed"           → format_source_fetch_failed
  other                                → format_source_fetch_failed (catch-all)

Description sync: agents/prompts.md §4.6.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_source_active_job,
    format_source_attached,
    format_source_denied_host,
    format_source_fetch_failed,
    format_source_too_large,
    format_source_unsupported_content_type,
    format_trip_not_found,
)

# Source: agents/prompts.md §4.6 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the user-research tool. When a user shares a URL or pastes text
they want the planner to use — call this tool.** Do not summarize the
research conversationally and forget it; this tool persists the content
to the trip so the Researcher agent uses it on the next refine.

Required: trip_id and ONE of {url, text}. Pass `url` when the user shares
a link; pass `text` when the user pastes raw content (e.g., "my friend
texted me these recommendations: ..."). Do not pass both.

Call this proactively when the user shares any of:
- a Reddit thread URL (e.g., r/IndiaTravel post)
- a blog/article URL (Substack, Medium, personal travel blog)
- a YouTube travel vlog URL (we store the URL; the planner sees the
  link in user_sources at refine time)
- a Google Maps saved list URL
- a TripAdvisor article or list URL
- raw pasted text the user describes as recommendations / research /
  "what my friend said"

Better to over-call than under-call. If the user shares two URLs in one
turn, call this tool twice (once per URL).

DO NOT call this for booking confirmations, hotel emails, flight
itineraries, or transactional content — those don't help the planner
make recommendations.

DO NOT call this if the user is just asking a question that references
a URL (e.g., "is this restaurant any good? <link>"). That's a
conversational question; the URL isn't research the user wants stored.

DO NOT call this for the URL of a Block already in the user's plan —
that's a citation, already stored as part of the trip.

Failure modes you should expect (the tool will tell you plainly which):
- The URL might be unreachable, paywalled, blocked, or return an error
  page. "Couldn't fetch the URL." DO NOT retry automatically; offer
  to take pasted text instead.
- The URL host may be denied (private IPs, localhost, cloud metadata
  endpoints). "Denied host for security reasons." Offer pasted text.
- The content may be the wrong format (image, video, PDF). "I can read
  HTML, plain text, or JSON — not <type>." Offer pasted text.
- The content may be too large (>2MB). "Too large." Offer a shorter
  excerpt.
- A planning job (refine, regenerate_day, add_constraint) may be in
  progress. "Can't add a source while a <kind> job is running." Tell
  the user to wait and check via get_trip.

Timing and what to say to the user:
- URL fetch returns in 2-5 seconds typically. Text passthrough returns
  in under 1 second.
- On success, tell the user the research was attached and will be
  used on the next refinement. Offer refine_trip if the user wants
  to apply the new research immediately.
- DO NOT claim the planner "has read" or "is using" the research
  until refine_trip runs. The content is stored for the NEXT
  refinement, not the current trip state.
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
    except Exception:  # noqa: BLE001
        return f"HTTP {resp.status_code}"
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return detail
    return f"HTTP {resp.status_code}"


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


async def add_source(
    *,
    trip_id: uuid.UUID,
    url: str | None = None,
    text: str | None = None,
) -> str:
    try:
        token = load_token(token_file=_token_file())
    except NoTokenError:
        from trip_mcp.tools._base import _DEV_CLI_HINT  # noqa: PLC0415

        return _DEV_CLI_HINT

    body: dict[str, Any] = {}
    if url is not None:
        body["url"] = url
    if text is not None:
        body["text"] = text

    with _http_client(token) as client:
        resp = client.post(f"/trips/{trip_id}/sources", json=body)

    # 200 happy path.
    if resp.status_code == 200:
        payload = _safe_json(resp) or {}
        return format_source_attached(
            trip_id=trip_id,
            content_type=str(payload.get("content_type", "?")),
            char_count=int(payload.get("char_count", 0)),
        )

    # 404 trip not found.
    if resp.status_code == 404:
        return format_trip_not_found(trip_id)

    body_json = _safe_json(resp)
    kind = body_json.get("kind") if isinstance(body_json, dict) else None

    # 409 active_job — slice-3.3 reuse pattern.
    if resp.status_code == 409 and kind == "active_job":
        return format_source_active_job(
            active_job_kind=str(body_json.get("active_job_kind", "")),
            active_job_id=str(body_json.get("active_job_id", "")),
        )

    # 400 denied_host — SSRF defense fired.
    if resp.status_code == 400 and kind == "denied_host":
        return format_source_denied_host(url or "the URL")

    # 413 too_large.
    if resp.status_code == 413 and kind == "too_large":
        byte_count = 0
        if isinstance(body_json, dict):
            raw = body_json.get("byte_count")
            if isinstance(raw, int):
                byte_count = raw
        return format_source_too_large(byte_count=byte_count)

    # 415 unsupported_content_type.
    if resp.status_code == 415 and kind == "unsupported_content_type":
        # Extract the offending content_type from the detail string when
        # the body doesn't carry a dedicated field. Conservative parse:
        # the detail is "unsupported Content-Type '<type>' for <url>".
        detail = str(body_json.get("detail", "")) if isinstance(body_json, dict) else ""
        content_type = "the URL's content type"
        if "'" in detail:
            parts = detail.split("'")
            if len(parts) >= 2:
                content_type = parts[1]
        return format_source_unsupported_content_type(content_type=content_type)

    # 502 fetch_failed AND catch-all for unexpected statuses.
    return format_source_fetch_failed(
        trip_id=trip_id,
        url=url or "(no URL)",
        reason=_extract_reason(resp),
    )
