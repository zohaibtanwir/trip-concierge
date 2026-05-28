"""Pure-function tests for the canonical tool response strings.

Per the spec-the-string discipline (same pattern as rate-limit constants
in slice 3.1): the user-facing text every tool returns is centralized in
trip_mcp.tools._responses. Tools call these functions, never assemble
strings inline. Future drift between tools is caught by these tests.

The strings must include the load-bearing phrases the LLM uses for
routing follow-up:
- success: the share URL, "~10 minutes", the trip_id (LLM context retention)
- partial failure: "couldn't be started" + "ask me to start planning again"
"""

from __future__ import annotations

import uuid

from trip_mcp.tools._responses import (
    format_clarification_needed,
    format_created_trip,
    format_partial_failure,
)

_TRIP_ID = uuid.UUID("abcabcab-1234-5678-9abc-abcabcabcabc")
_SHARE_URL = f"https://tripconcierge.app/trips/{_TRIP_ID}"


def test_created_trip_includes_trip_id_share_url_and_timing() -> None:
    text = format_created_trip(
        trip_id=_TRIP_ID,
        destination="Goa",
        budget_total=40000,
        currency="INR",
        share_url=_SHARE_URL,
    )
    assert str(_TRIP_ID) in text
    assert _SHARE_URL in text
    assert "Goa" in text
    # The ~10 minute expectation is the load-bearing UX promise.
    assert "10 minutes" in text
    # The follow-up hook tells the LLM what tool to suggest next.
    assert "check" in text.lower()


def test_created_trip_renders_budget_in_currency_when_present() -> None:
    text = format_created_trip(
        trip_id=_TRIP_ID,
        destination="Goa",
        budget_total=40000,
        currency="INR",
        share_url=_SHARE_URL,
    )
    # We want the budget to surface in the message at all — exact format
    # is a UX detail, but the number and currency code should both appear.
    assert "40" in text  # 40000 or 40,000 — formatter's choice
    assert "INR" in text


def test_created_trip_omits_budget_when_none() -> None:
    """If the user didn't supply a budget, the response must not invent one."""
    text = format_created_trip(
        trip_id=_TRIP_ID,
        destination="Goa",
        budget_total=None,
        currency="USD",
        share_url=_SHARE_URL,
    )
    assert "USD" not in text
    assert "0 USD" not in text
    assert "$0" not in text
    # Still includes the timing + share URL.
    assert "10 minutes" in text
    assert _SHARE_URL in text


def test_clarification_needed_for_destination_or_vibe_offers_concrete_examples() -> None:
    """The most common clarification path: the LLM called the tool without
    extracting either a destination or a vibe. The response must offer
    concrete examples so the user can fill the gap in one turn — not just
    say "I need more info."
    """
    text = format_clarification_needed(["destination_or_vibe"])
    # First-person, conversational, the LLM will echo this.
    assert text.startswith("I need")
    # Names BOTH fields the LLM could have extracted, with concrete examples.
    assert "destination" in text.lower()
    assert "vibe" in text.lower()
    # At least one place-example + one vibe-example so the user has guidance.
    assert "Goa" in text or "Europe" in text
    assert "beach" in text.lower() or "foodie" in text.lower()


def test_clarification_needed_falls_back_for_unknown_missing_keys() -> None:
    """Defensive fallback — if future tools call this with field names not
    in the canonical mapping, the response still surfaces what's missing
    rather than crashing.
    """
    text = format_clarification_needed(["some_future_field", "another"])
    assert "some_future_field" in text
    assert "another" in text


def test_partial_failure_names_the_problem_and_retry_path() -> None:
    """When POST /trips succeeds but POST /plan fails, the user must know:
    (1) the trip exists, (2) the plan didn't start, (3) how to retry.
    """
    text = format_partial_failure(trip_id=_TRIP_ID, share_url=_SHARE_URL)
    assert str(_TRIP_ID) in text
    assert _SHARE_URL in text
    # Names the failure mode explicitly.
    assert "couldn't be started" in text or "could not be started" in text
    # Names the retry path.
    assert "start planning again" in text.lower() or "retry" in text.lower()
    # Does NOT contain the ~10 minutes promise — the job didn't start.
    assert "10 minutes" not in text


# ---------------------------------------------------------------------------
# Slice 3.3 commit 5: response formatters for get_trip / refine_trip /
# regenerate_day. Five pure-function tests asserting the load-bearing
# phrasings the LLM consumes.
# ---------------------------------------------------------------------------


def test_trip_planning_response_mentions_in_progress_and_progress_message() -> None:
    from trip_mcp.tools._responses import format_trip_planning

    text = format_trip_planning(
        trip_id=_TRIP_ID,
        destination="Goa",
        progress_message="Researcher pass 1: searching Goa venues",
    )
    assert str(_TRIP_ID) in text
    assert "Goa" in text
    # Conveys "not done yet" — accept any of these conceptual signals.
    lower = text.lower()
    assert "planned" in lower or "progress" in lower or "still" in lower
    assert "Researcher" in text
    # Must NOT promise it's ready — same prohibition discipline as 4.1.
    assert "ready" not in lower
    assert "done" not in lower


def test_trip_planning_without_progress_message_still_renders() -> None:
    from trip_mcp.tools._responses import format_trip_planning

    text = format_trip_planning(trip_id=_TRIP_ID, destination="Goa", progress_message=None)
    assert "Goa" in text
    lower = text.lower()
    assert "planned" in lower or "progress" in lower or "still" in lower


def test_trip_succeeded_renders_day_by_day_from_actual_data() -> None:
    from trip_mcp.tools._responses import format_trip_succeeded

    full_trip = {
        "id": str(_TRIP_ID),
        "destination": "Goa",
        "currency": "INR",
        "days": [
            {
                "day_number": 1,
                "date": "2026-07-15",
                "summary": "Beach day",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Anjuna Beach",
                        "start_time": "09:00",
                        "duration_minutes": 120,
                        "est_cost": "0.00",
                    },
                    {
                        "order": 2,
                        "type": "meal",
                        "venue_name": "Cafe Bodega",
                        "start_time": "13:00",
                        "duration_minutes": 60,
                        "est_cost": "400.00",
                    },
                ],
            },
        ],
    }
    text = format_trip_succeeded(full_trip)
    assert str(_TRIP_ID) in text
    assert "Goa" in text
    assert "Day 1" in text
    assert "Anjuna Beach" in text
    assert "Cafe Bodega" in text


def test_trip_failed_names_error_category_and_offers_next_steps() -> None:
    """The slice-thesis load-bearer. The string must:
    - surface failure plainly (no softening)
    - render the Q6 error-class CATEGORY, not the raw JobRun error text
    - NOT leak internal class names, Pydantic URLs, or raw exception
      details to the user-facing message
    - offer concrete retry options

    Slice 3.3 commit 6 (Q6 alignment): format_trip_failed maps known error
    classes to user-friendly categories. The full raw error stays in
    JobRun.error for backend debugging via SQL; only the category reaches
    the LLM.
    """
    from trip_mcp.tools._responses import format_trip_failed

    raw_error = (
        "ValidationError: 1 validation error for TripPlan\n"
        "days\n  Field required [type=missing, input_value={}, input_type=dict]\n"
        "    For further information visit https://errors.pydantic.dev/2.12/v/missing"
    )
    text = format_trip_failed(trip_id=_TRIP_ID, destination="Goa", error=raw_error)

    assert str(_TRIP_ID) in text
    assert "Goa" in text

    # Names failure plainly.
    assert "failed" in text.lower() or "didn't complete" in text.lower()

    # Category text from the Q6 mapping is present.
    assert "the planner produced an incomplete itinerary" in text

    # Raw error details, class names, and internal URLs are NOT present —
    # the LLM should never see them.
    assert "ValidationError" not in text
    assert "Pydantic" not in text
    assert "pydantic" not in text
    assert "errors.pydantic.dev" not in text
    assert "1 validation error for TripPlan" not in text
    assert "Field required" not in text
    assert "input_value={}" not in text

    # Offers concrete next steps.
    assert "create_trip" in text or "try again" in text.lower()

    # Must NOT use forbidden softer language.
    for softer in ("almost there", "still working", "not quite finished"):
        assert softer not in text.lower(), (
            f"forbidden softer-language phrase {softer!r} leaked into failed response"
        )


def test_trip_failed_unknown_error_class_falls_through_to_default() -> None:
    """Defensive fallback — when the JobRun.error class isn't in the
    canonical _ERROR_CATEGORIES map, format_trip_failed must render
    "an internal error" and still NOT leak the raw message.
    """
    from trip_mcp.tools._responses import format_trip_failed

    text = format_trip_failed(
        trip_id=_TRIP_ID,
        destination="Goa",
        error="CustomNeverSeenError: something went sideways internally",
    )
    # Fallback category.
    assert "an internal error" in text
    # Raw message and class name absent.
    assert "CustomNeverSeenError" not in text
    assert "sideways" not in text


def test_trip_failed_timeout_class_maps_to_timeout_category() -> None:
    """Spot-check a second mapped class so the dict isn't accidentally
    one-entry. If TimeoutError gets dropped during a future refactor
    this fails loudly.
    """
    from trip_mcp.tools._responses import format_trip_failed

    text = format_trip_failed(
        trip_id=_TRIP_ID,
        destination="Goa",
        error="TimeoutError: crew kickoff exceeded 900s",
    )
    assert "the planner ran out of time" in text
    assert "TimeoutError" not in text
    assert "900s" not in text


def test_regenerate_day_not_ready_branches_on_state() -> None:
    """The function takes real PlanStatus state values: queued/running/
    cancelling/done/failed/cancelled. "planning" is the abstraction the
    user-facing §4.2 description uses; this layer sees the concrete states."""
    from trip_mcp.tools._responses import format_regenerate_day_not_ready

    # In-progress branch — running maps to "still being planned" UX.
    running_text = format_regenerate_day_not_ready("running")
    lower_r = running_text.lower()
    assert "planned" in lower_r or "progress" in lower_r or "still" in lower_r
    assert "get_trip" in running_text

    queued_text = format_regenerate_day_not_ready("queued")
    assert "get_trip" in queued_text

    # Failed branch — offers create_trip/refine_trip recovery.
    failed_text = format_regenerate_day_not_ready("failed")
    assert "create_trip" in failed_text or "refine_trip" in failed_text
