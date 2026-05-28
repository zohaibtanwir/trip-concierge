"""Canonical tool response strings.

The user-facing text every MCP tool returns is centralized here. Tools
call these functions; they never assemble user-facing strings inline.

Why: MCP tool results render directly in Claude Desktop. Inconsistent
phrasing across tools makes the product feel disjointed. Centralizing
also makes the strings testable as pure functions (see
tests/test_responses.py) — drift between tools is caught immediately
instead of discovered by users.

Same spec-the-string discipline that the rate-limit constants in
backend/app/routes/auth.py use for slice 4.1.
"""

from __future__ import annotations

import uuid
from typing import Any


def format_created_trip(
    *,
    trip_id: uuid.UUID,
    destination: str,
    budget_total: float | int | None,
    currency: str,
    share_url: str,
) -> str:
    """Successful create_trip — trip row + plan enqueue both 2xx.

    Load-bearing phrases (asserted by tests):
    - the share URL on its own line so Claude Desktop renders it as a link
    - "10 minutes" so the LLM sets the user's expectation correctly
    - the trip_id (LLM keeps it in context for the next tool call)
    - "check back" so the LLM knows to suggest get_trip next
    """
    budget_line = ""
    if budget_total is not None:
        budget_line = f" with your {budget_total:,.0f} {currency} budget"

    return (
        f"Created your {destination} trip — id {trip_id}.\n"
        f"\n"
        f"Working on the plan{budget_line}. The full itinerary will be ready "
        f"in about 10 minutes.\n"
        f"\n"
        f"View at: {share_url}\n"
        f"\n"
        f"Ask me anytime to check back on the trip status."
    )


def format_partial_failure(*, trip_id: uuid.UUID, share_url: str) -> str:
    """POST /trips succeeded, POST /plan failed.

    The user must know: (1) the trip exists, (2) the plan job didn't
    start, (3) how to retry. The "10 minutes" promise is NOT included —
    nothing is running.
    """
    return (
        f"Your trip was created (id {trip_id}) but the planning job "
        f"couldn't be started.\n"
        f"\n"
        f"View at: {share_url}\n"
        f"\n"
        f"Ask me to start planning again to retry."
    )


def format_create_failed(reason: str) -> str:
    """POST /trips failed before a trip row was created. No trip_id to
    return; the LLM should restate the user's request or ask for missing
    fields based on the reason.
    """
    return f"I couldn't create the trip — {reason}.\n\nWant to try again with different details?"


def format_clarification_needed(missing: list[str]) -> str:
    """Tool-response string when the LLM called create_trip without enough
    information to plan a trip.

    First-person tone is deliberate — Claude Desktop's LLM reads this
    response and echoes it conversationally to the user. The pattern
    (soft-validation responses in _responses.py) carries through 3.3-3.5.
    """
    if missing == ["destination_or_vibe"]:
        return (
            "I need a bit more to plan this — either a destination "
            "(like 'Goa' or 'somewhere in Europe') or a vibe "
            "(like 'chill beach trip' or 'foodie adventure'). "
            "What did you have in mind?"
        )
    return f"I need more information to plan this trip: {', '.join(missing)}."


# ---------------------------------------------------------------------------
# Slice 3.3 commit 5: response formatters for get_trip, refine_trip,
# regenerate_day. The state-aware formatters in this section embody the
# slice thesis (visibility before reliability) — get_trip's failed-state
# response carries the prohibition-honoring language the §4.2 description
# tells the LLM to use.
# ---------------------------------------------------------------------------


def format_trip_planning(
    *,
    trip_id: uuid.UUID,
    destination: str,
    progress_message: str | None,
) -> str:
    """get_trip response when state ∈ {queued, running, cancelling}."""
    progress_line = ""
    if progress_message:
        progress_line = f"Current step: {progress_message}\n\n"
    return (
        f"Your {destination} trip (id {trip_id}) is still being planned.\n"
        f"\n"
        f"{progress_line}"
        f"The full itinerary should be available in a few more minutes. "
        f"Ask me to check again then."
    )


def format_trip_succeeded(full_trip: dict[str, Any]) -> str:
    """get_trip response when state=done and approved=true.

    Renders the day-by-day itinerary from the actual data. NO fabrication —
    if a Day has zero Blocks, the response says so plainly.
    """
    trip_id = full_trip.get("id", "unknown")
    destination = full_trip.get("destination", "your")
    days = full_trip.get("days") or []

    lines = [f"Your {destination} trip is ready! (id {trip_id})", ""]
    if not days:
        lines.append("The trip has no days planned — this is unusual; the data may be incomplete.")
    else:
        for day in days:
            day_num = day.get("day_number", "?")
            date = day.get("date") or ""
            date_part = f" ({date})" if date else ""
            lines.append(f"Day {day_num}{date_part}:")
            blocks = day.get("blocks") or []
            if not blocks:
                lines.append("  (no blocks yet for this day)")
            else:
                for block in blocks:
                    venue = block.get("venue_name", "?")
                    start = block.get("start_time") or ""
                    dur = block.get("duration_minutes", 0)
                    cost = block.get("est_cost") or "0"
                    start_part = f"{start} — " if start else ""
                    lines.append(f"  {start_part}{venue} ({dur} min, est {cost})")
            lines.append("")

    return "\n".join(lines).rstrip()


# Slice 3.3 commit 6 (Q6 alignment): map JobRun.error's exception class to a
# user-friendly category. The full raw error stays in JobRun.error for backend
# debugging via SQL; only the category text reaches the LLM, which prevents
# internal class names, Pydantic URLs, and traceback fragments from leaking
# into Claude Desktop responses.
_ERROR_CATEGORIES: dict[str, str] = {
    "ValidationError": "the planner produced an incomplete itinerary",
    "TimeoutError": "the planner ran out of time",
    "RateLimitError": "an API rate limit was hit",
    "APIError": "an upstream API failure",
    "_default": "an internal error",
}


def _categorize_error(error: str | None) -> str | None:
    """Return the user-friendly category for a JobRun.error string.

    JobRun.error is formatted by the worker as "<ClassName>: <message>"
    (see app/worker.py _write_job_run_session callers). Split on the first
    colon to recover the class name, then look it up. Unknown classes fall
    through to _default — honest degradation, not silent failure.

    Returns None if `error` is None/empty so the caller can suppress the
    "what went wrong" line entirely.
    """
    if not error:
        return None
    class_name = error.split(":", 1)[0].strip() if ":" in error else error.strip()
    return _ERROR_CATEGORIES.get(class_name, _ERROR_CATEGORIES["_default"])


def format_trip_failed(
    *,
    trip_id: uuid.UUID,
    destination: str,
    error: str | None,
) -> str:
    """get_trip response when state=failed.

    Slice-thesis load-bearer — names "failed" plainly, no softer language,
    offers concrete next steps. Per §4.2 description: the LLM is told to
    surface this verbatim.

    Per the Q6 design (file-tree session), the raw JobRun.error text is
    NOT exposed to the LLM. Only the mapped error category is. This keeps
    internal exception details (Pydantic URLs, validation tracebacks,
    class names) out of the user-facing response.
    """
    category = _categorize_error(error)
    error_line = f"What went wrong: {category}.\n\n" if category else ""
    return (
        f"Your {destination} trip's planning didn't complete successfully (id {trip_id}).\n"
        f"\n"
        f"{error_line}"
        f"You can try create_trip again to start over, or refine_trip if "
        f"you want to adjust the inputs and retry."
    )


def format_trip_not_found(trip_id: uuid.UUID) -> str:
    """get_trip response when backend returned 404."""
    return (
        f"I couldn't find trip {trip_id}. It may have been deleted, or the "
        f"id may be wrong. Want to start a new one with create_trip?"
    )


def format_refine_enqueued(*, trip_id: uuid.UUID, destination: str) -> str:
    """refine_trip response when POST /refine returns 202."""
    return (
        f"Started refining your {destination} trip (id {trip_id}).\n"
        f"\n"
        f"The refinement runs in the background and takes about 10 minutes. "
        f"Locked blocks are preserved automatically. Ask me to check the "
        f"trip status via get_trip in a few minutes."
    )


def format_refine_failed(*, trip_id: uuid.UUID, reason: str) -> str:
    """refine_trip response when the backend POST didn't return 202."""
    return (
        f"I couldn't start the refinement for trip {trip_id} — {reason}.\n"
        f"\n"
        f"Want to try again with different wording?"
    )


def format_regenerate_enqueued(*, trip_id: uuid.UUID, day_number: int, destination: str) -> str:
    """regenerate_day response when POST /regenerate returns 202."""
    return (
        f"Started regenerating Day {day_number} of your {destination} trip "
        f"(id {trip_id}).\n"
        f"\n"
        f"This takes about 3-5 minutes — faster than a full refinement "
        f"because the scope is one day. Locked blocks are preserved. Ask "
        f"me to check the trip status via get_trip in a few minutes."
    )


def format_regenerate_failed(*, trip_id: uuid.UUID, reason: str) -> str:
    return (
        f"I couldn't start the regeneration for trip {trip_id} — {reason}.\n"
        f"\n"
        f"Want to try again, or check the trip status via get_trip first?"
    )


def format_regenerate_day_not_ready(state: str) -> str:
    """Pre-call gate refusal — slice 3.3 commit 4 design Q3.

    When regenerate_day is called on a trip whose state isn't 'done', we
    refuse here before any HTTP enqueue. Saves a backend round-trip and
    surfaces a clear next-step the LLM can echo to the user.
    """
    if state in ("queued", "running"):
        return (
            "I can't regenerate a day yet — the trip is still being planned. "
            "Try get_trip in a few minutes; once it's ready I can regenerate "
            "any day you want."
        )
    if state == "failed":
        return (
            "I can't regenerate a day on a trip whose initial planning didn't "
            "complete. Try create_trip again from scratch, or refine_trip if "
            "you want to adjust the inputs."
        )
    return (
        "This trip is in a state I can't regenerate from — likely cancelled "
        "or no longer active. Use create_trip to start fresh."
    )
