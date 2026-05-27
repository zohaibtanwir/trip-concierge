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
