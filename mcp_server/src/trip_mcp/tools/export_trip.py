"""export_trip MCP tool — slice 3.5 commit 3.

Single backend call: GET /trips/{id}/export?format=json|markdown.
Branches on format for the right formatter:

  200 + format="markdown" → format_export_succeeded_markdown
  200 + format="json"     → format_export_succeeded_json (opt-in disclosure)
  404                     → format_export_failed
  401 / 422 / other       → format_export_failed (catch-all)

The backend's Literal["json","markdown"] enforces the format at
the type layer (422 on any other value, per slice-3.4a discipline:
single rare error path doesn't justify the kind-structured-body
pattern). PDF + whatsapp + google_maps formats are deferred to
trip-concierge-de6 (P2, PDF) + trip-concierge-dzg (P3,
whatsapp+google_maps).

Description sync: agents/prompts.md §4.11.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from trip_mcp.auth import NoTokenError, load_token
from trip_mcp.config import backend_url, default_token_file
from trip_mcp.tools._responses import (
    format_export_failed,
    format_export_succeeded_json,
    format_export_succeeded_markdown,
)

# Source: agents/prompts.md §4.11 — keep in sync per
# .claude/rules/mcp-tool-description-style.md.
DESCRIPTION = """
**This is the export tool. When the user wants their trip in a
portable format — use this tool.** Do not synthesize the export
content conversationally; this tool returns the canonical rendering
the backend produces, so future re-exports stay byte-identical.

Required: trip_id and format. Format is one of:
- "json" — full structured data, suitable for programmatic re-import
- "markdown" — human-readable day-by-day, pasteable into Notion /
  WhatsApp / Apple Notes / any text app

Call this for instructions like:
- "give me a Markdown version I can paste into Notion"
- "export this as JSON" (data-pipeline / re-import use cases)
- "I want to text my partner the full itinerary"
- "send me a copy I can paste into my notes app"

DO NOT use this for sharing — use share_trip instead. share_trip
returns a URL; export_trip returns the content. Different UX.

DO NOT use this for printable/PDF formats yet. PDF + map snapshots
+ QR codes is planned for v1.0b. If the user asks for PDF, tell
them honestly: not yet, but Markdown is portable enough for most
text-paste use cases.

DO NOT use this for WhatsApp-specific formatting or Google Maps
URLs. Markdown is close to WhatsApp-flavored text but not identical;
Google Maps URL generation is planned for v1.0c. If the user asks,
suggest pasting the Markdown export.

DO NOT use this if the trip isn't ready yet. The export of a
half-planned trip would be misleading. Call get_trip first if
unsure.

Timing and what to say to the user:
- The tool returns in 1-2 seconds (pure DB read + stdlib formatting).
- For Markdown, present the full content inline — Claude Desktop
  renders Markdown nicely. For JSON, mention the format briefly
  but don't paste the full JSON unless the user specifically asks
  to see it (it's noisy).
- DO NOT claim the export "captures" the trip if state isn't done.
  Tell the user honestly the export reflects current state, which
  may be partial.
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


async def export_trip(*, trip_id: uuid.UUID, format: str = "markdown") -> str:
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
        resp = client.get(f"/trips/{trip_id}/export", params={"format": format})

    if resp.status_code != 200:
        return format_export_failed(trip_id=trip_id, reason=_extract_reason(resp))

    if format == "markdown":
        # destination isn't separately surfaced by the backend's markdown
        # body — the heading is the first line. Pass a generic
        # placeholder; the formatter's wrapper text doesn't depend on it.
        return format_export_succeeded_markdown(
            trip_id=trip_id, destination="your", content=resp.text
        )

    # JSON branch — opt-in disclosure, no inline body.
    return format_export_succeeded_json(trip_id=trip_id, char_count=len(resp.text))
