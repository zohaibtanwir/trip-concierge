"""Trip export — JSON + Markdown rendering for export_trip MCP tool.

Slice 3.5 commit 1. Stdlib only; no new deps for v1.0a.

The service takes TripFullRead (the same Pydantic schema GET /trips/
{id}/full returns) and emits a string the route layer ships to the
client. Decoupling from SQLAlchemy via the Pydantic boundary keeps
the renderer testable without DB session setup and pins the data
contract: change the schema → update the renderer in lockstep.

Format-design choice (pinned by test_render_markdown_omits_constraints):
- JSON includes everything: constraints, pace, currency, user_id, etc.
  Programmatic re-import target.
- Markdown is the human-pasteable surface: day-by-day blocks, venue
  names, source URLs. Drops the constraints/pace/currency envelope
  because those don't help a user reading Notion / WhatsApp / Apple
  Notes.

Honest-broken discipline (slice-3.3 carryover): empty days / empty
blocks render with explicit "no days planned" / "no blocks yet"
lines rather than silently omitting. The qek bug can produce trips
with zero days; the export must surface that state honestly.

PDF + whatsapp + google_maps formats are deferred — see tickets
trip-concierge-de6 (P2, PDF) and trip-concierge-dzg (P3,
whatsapp+google_maps).
"""

from __future__ import annotations

import json

from app.schemas.day import BlockRead, DayRead
from app.schemas.trip import TripFullRead


def render_json(trip: TripFullRead) -> str:
    """Full structured dump. Pydantic's model_dump(mode='json')
    normalizes Decimal/date/datetime/UUID to strings — no custom
    encoder needed.

    Indent=2 for human inspectability; the caller can re-minify if
    bandwidth matters. The serialized output round-trips through
    json.loads (pinned by test).
    """
    return json.dumps(trip.model_dump(mode="json"), indent=2)


def render_markdown(trip: TripFullRead) -> str:
    """Human-pasteable day-by-day rendering.

    Structure:
        # <destination>
        <date_range>

        ## Day N (date)
        <summary>

        - HH:MM — <venue_name> (Nmin, <cost> <currency>)
          Source: <url>

    Optional fields (start_time=None, est_cost=None, etc.) are
    elided rather than rendered as literal "None". Empty days /
    blocks surface with explicit gap lines.
    """
    lines: list[str] = []

    # Header: destination + optional date range.
    lines.append(f"# {trip.destination}")
    date_range = _date_range_line(trip)
    if date_range:
        lines.append(date_range)
    lines.append("")

    if not trip.days:
        lines.append("_This trip has no days planned yet._")
        return "\n".join(lines).rstrip()

    for day in trip.days:
        lines.extend(_render_day(day))
        lines.append("")

    return "\n".join(lines).rstrip()


def _date_range_line(trip: TripFullRead) -> str | None:
    """Optional `start_date – end_date` line. Returns None if neither
    date is set so the section disappears rather than rendering
    "None – None"."""
    if trip.start_date is None and trip.end_date is None:
        return None
    start = trip.start_date.isoformat() if trip.start_date is not None else "?"
    end = trip.end_date.isoformat() if trip.end_date is not None else "?"
    return f"{start} – {end}"


def _render_day(day: DayRead) -> list[str]:
    """Render one Day section. Returns lines (no trailing blank — the
    caller adds the spacing).
    """
    date_part = f" ({day.date.isoformat()})" if day.date is not None else ""
    lines = [f"## Day {day.day_number}{date_part}"]
    if day.summary:
        lines.append(day.summary)
    lines.append("")

    if not day.blocks:
        lines.append("_No blocks yet for this day._")
        return lines

    for block in day.blocks:
        lines.extend(_render_block(block))
    return lines


def _render_block(block: BlockRead) -> list[str]:
    """Render one Block. Skip optional fields that are None so the
    output stays clean.
    """
    parts: list[str] = []
    if block.start_time is not None:
        parts.append(block.start_time)
    parts.append(block.venue_name)
    main_line = " — ".join(parts) if len(parts) > 1 else parts[0]

    meta_bits: list[str] = []
    # Elide duration for blocks with zero/missing duration — rendering
    # "0min" inline would suggest a real measurement rather than missing data.
    if block.duration_minutes:
        meta_bits.append(f"{block.duration_minutes}min")
    if block.est_cost is not None:
        meta_bits.append(f"{block.est_cost} {block.currency}")
    if meta_bits:
        main_line = f"{main_line} ({', '.join(meta_bits)})"

    lines = [f"- {main_line}"]
    for source in block.sources:
        if source.url:
            lines.append(f"  Source: {source.url}")
    return lines
