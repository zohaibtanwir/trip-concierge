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


# ---------------------------------------------------------------------------
# Slice 3.4a commit 5: response formatters for add_constraint and
# find_alternative. Eight new formatters; tests pin the shape, the
# prohibition-discipline phrasing, and the cross-tool consistency with
# slice-3.3 formatters.
# ---------------------------------------------------------------------------


def test_constraint_enqueued_echoes_text_and_routes_to_get_trip() -> None:
    from trip_mcp.tools._responses import format_constraint_enqueued

    text = format_constraint_enqueued(trip_id=_TRIP_ID, constraint_text="I'm vegetarian")
    assert str(_TRIP_ID) in text
    assert "vegetarian" in text
    assert "get_trip" in text
    assert "10 minutes" in text or "minutes" in text.lower()
    # Prohibition discipline — must NOT claim the plan "now satisfies".
    assert "now satisfies" not in text.lower()
    assert "applied" not in text.lower()


def test_constraint_failed_names_failure_without_claiming_added() -> None:
    from trip_mcp.tools._responses import format_constraint_failed

    text = format_constraint_failed(trip_id=_TRIP_ID, reason="something broke")
    assert str(_TRIP_ID) in text
    assert "something broke" in text
    assert "couldn't" in text.lower() or "could not" in text.lower()
    # Must NOT claim the constraint was added.
    assert "added" not in text.lower() or "couldn't" in text.lower()


def test_alternative_succeeded_renders_three_ranked_with_sources() -> None:
    from trip_mcp.tools._responses import format_alternative_succeeded

    alternatives = [
        {
            "venue_name": f"Spot {i}",
            "type": "meal",
            "duration_minutes": 60,
            "est_cost": 600.0,
            "currency": "INR",
            "source_urls": [f"https://example.com/{i}"],
            "rationale": f"fits constraint i={i} stuff stuff",
        }
        for i in range(1, 4)
    ]
    text = format_alternative_succeeded(
        alternatives=alternatives, block_venue_name="Original Restaurant"
    )

    # 3 venues with ranking numerals.
    for i in range(1, 4):
        assert f"Spot {i}" in text
        assert f"{i}." in text
        assert f"https://example.com/{i}" in text

    # Original venue named so user knows what they're replacing.
    assert "Original Restaurant" in text
    # Follow-up question — routes user to pick + we call refine_trip.
    assert "which" in text.lower() or "pick" in text.lower()
    # Prohibition discipline — must NOT claim any one is "the best".
    assert "is the best" not in text.lower()
    assert "perfect" not in text.lower()


def test_alternative_active_job_surfaces_label_and_routes_to_get_trip() -> None:
    from trip_mcp.tools._responses import format_alternative_active_job

    text = format_alternative_active_job(active_job_kind="refine", active_job_id="refine-existing")
    # Surfaces the slice-3.3 label.
    assert "refinement" in text.lower()
    assert "refine-existing" in text
    assert "get_trip" in text
    # No alternatives claimed.
    assert "Spot" not in text


def test_alternative_active_job_handles_unknown_kind_with_generic_label() -> None:
    """Defensive — if backend ever returns a new JobKind we don't know
    yet, the formatter must degrade to a generic label rather than crash.
    """
    from trip_mcp.tools._responses import format_alternative_active_job

    text = format_alternative_active_job(active_job_kind="newkind", active_job_id="x")
    # Some generic label, not a Python KeyError.
    assert "background" in text.lower() or "newkind" in text.lower()


def test_alternative_not_ready_branches_on_state() -> None:
    from trip_mcp.tools._responses import format_alternative_not_ready

    never = format_alternative_not_ready("never_planned").lower()
    assert "hasn't been planned" in never or "not been planned" in never

    failed = format_alternative_not_ready("failed").lower()
    assert "didn't complete" in failed or "did not complete" in failed

    other = format_alternative_not_ready("cancelled").lower()
    assert "cancelled" in other or "start fresh" in other


def test_alternative_block_not_found_routes_to_get_trip() -> None:
    from trip_mcp.tools._responses import format_alternative_block_not_found

    text = format_alternative_block_not_found(trip_id=_TRIP_ID, block_id=uuid.uuid4())
    assert str(_TRIP_ID) in text
    assert "get_trip" in text
    assert "block" in text.lower()


def test_alternative_timeout_names_failure_and_asks_user_to_retry() -> None:
    from trip_mcp.tools._responses import format_alternative_timeout

    text = format_alternative_timeout(elapsed_seconds=90.0)
    assert "90" in text
    # Names failure plainly.
    assert "timed out" in text.lower() or "timeout" in text.lower()
    # Puts retry choice on the user.
    assert "try again" in text.lower() or "retry" in text.lower()
    # Prohibition discipline.
    assert "almost" not in text.lower()
    assert "still working" not in text.lower()


def test_alternative_failed_catchall_includes_reason() -> None:
    from trip_mcp.tools._responses import format_alternative_failed

    text = format_alternative_failed(trip_id=_TRIP_ID, reason="upstream API error")
    assert str(_TRIP_ID) in text
    assert "upstream API error" in text
    assert "couldn't" in text.lower() or "could not" in text.lower()


# ---------------------------------------------------------------------------
# Slice 3.4b commit 4: response formatters for add_source and
# explain_recommendation. Each formatter test pins its load-bearing
# property — the highest-traffic surface in the slice deserves dense
# per-shape coverage.
# ---------------------------------------------------------------------------


def test_source_attached_echoes_char_count_and_routes_to_refine() -> None:
    from trip_mcp.tools._responses import format_source_attached

    text = format_source_attached(
        trip_id=_TRIP_ID, content_type="url_fetched/html", char_count=4321
    )
    assert str(_TRIP_ID) in text
    # char_count with humanized formatting OR raw int.
    assert "4,321" in text or "4321" in text
    assert "url_fetched/html" in text
    assert "refine_trip" in text
    # Prohibition discipline — must NOT claim the planner already used it.
    for forbidden in ("has read", "is using", "now applied", "already applied"):
        assert forbidden not in text.lower()


def test_source_fetch_failed_offers_paste_without_claiming_attached() -> None:
    from trip_mcp.tools._responses import format_source_fetch_failed

    text = format_source_fetch_failed(
        trip_id=_TRIP_ID,
        url="https://example.com/article",
        reason="timeout",
    )
    assert str(_TRIP_ID) in text
    assert "https://example.com/article" in text
    assert "timeout" in text
    assert "paste" in text.lower()
    assert "couldn't" in text.lower() or "could not" in text.lower()
    # Must NOT claim attached.
    assert "attached" not in text.lower() or "couldn't" in text.lower()


def test_source_denied_host_explains_security_reason() -> None:
    from trip_mcp.tools._responses import format_source_denied_host

    text = format_source_denied_host("http://localhost/internal")
    assert "http://localhost/internal" in text
    # Names the security reason, not just "denied".
    lower = text.lower()
    assert "private ip" in lower or "metadata" in lower or "security" in lower
    # Offers paste alternative.
    assert "paste" in lower or "different" in lower


def test_source_too_large_surfaces_byte_count_and_2mb_cap() -> None:
    from trip_mcp.tools._responses import format_source_too_large

    text = format_source_too_large(byte_count=3_500_000)
    # Humanized or raw byte count.
    assert "3,500,000" in text or "3500000" in text or "3.5" in text
    # The 2 MB cap is mentioned so the user understands the scale.
    assert "2 MB" in text or "2MB" in text or "2,000,000" in text
    # Offers shorter excerpt path.
    assert "excerpt" in text.lower() or "shorter" in text.lower() or "paste" in text.lower()


def test_source_unsupported_content_type_explains_format_constraint() -> None:
    from trip_mcp.tools._responses import format_source_unsupported_content_type

    text = format_source_unsupported_content_type(content_type="image/png")
    assert "image/png" in text
    # Names the supported types so the user understands the constraint.
    lower = text.lower()
    assert "html" in lower or "plain text" in lower or "json" in lower
    assert "paste" in lower or "different url" in lower


def test_source_active_job_surfaces_label_and_routes_to_get_trip() -> None:
    from trip_mcp.tools._responses import format_source_active_job

    text = format_source_active_job(active_job_kind="refine", active_job_id="refine-existing")
    assert "refinement" in text.lower(), "must surface KIND_LABELS['refine']='refinement'"
    assert "refine-existing" in text
    assert "get_trip" in text
    # Prohibition discipline.
    assert "attached" not in text.lower() or "can't" in text.lower()


def test_source_active_job_handles_unknown_kind_with_generic_label() -> None:
    """Defensive — if backend ships a new JobKind we don't know yet,
    the formatter degrades to a generic label rather than crashing.
    Mirrors test_alternative_active_job_handles_unknown_kind.
    """
    from trip_mcp.tools._responses import format_source_active_job

    text = format_source_active_job(active_job_kind="newkind", active_job_id="x")
    assert "background" in text.lower() or "newkind" in text.lower()


def test_explain_with_rationale_renders_venue_block_type_rationale_sources() -> None:
    from trip_mcp.tools._responses import format_explain_with_rationale

    sources = [
        {
            "url": "https://reddit.com/r/IndiaTravel/anjuna",
            "excerpt": "Locals say Anjuna is the best for sunsets",
            "confidence_score": 0.85,
        },
        {
            "url": "https://blog.example.com/goa",
            "excerpt": "Avoid Calangute, hit Anjuna for sunset",
            "confidence_score": 0.7,
        },
    ]
    text = format_explain_with_rationale(
        venue_name="Anjuna Beach",
        block_type="venue",
        rationale="Goa's most iconic sunset beach.",
        sources=sources,
        user_source_matches=[],
    )

    assert "Anjuna Beach" in text
    assert "venue" in text  # block_type surfaces
    assert "Goa's most iconic sunset beach." in text
    # Both source URLs render.
    assert "https://reddit.com/r/IndiaTravel/anjuna" in text
    assert "https://blog.example.com/goa" in text
    # Confidence shown somehow.
    assert "0.85" in text or "85" in text
    # No formatter-level prohibition on superlatives here: the formatter
    # renders rationale + excerpts verbatim, and external strings may
    # contain "best"/"perfect". The "don't synthesize" discipline lives
    # at the §4.8 description level (where it's enforceable), not at
    # the formatter (which has no way to know if an external string is
    # the crew's words or its own).


def test_explain_with_gap_uses_literal_qek_message_for_lockstep_with_description() -> None:
    """The single most load-bearing formatter test in this slice.

    §4.8 description tells the LLM: "When you see that gap message, DO NOT
    synthesize a plausible rationale". For that instruction to be
    actionable, the literal "rationale wasn't captured" wording must
    appear in the tool output the LLM reads. If the formatter wording
    drifts, the description's "when you see" guidance points at nothing.
    """
    from trip_mcp.tools._responses import format_explain_with_gap

    sources = [
        {
            "url": "https://reddit.com/r/IndiaTravel/anjuna",
            "excerpt": "Locals say Anjuna is the best",
            "confidence_score": 0.85,
        },
    ]
    text = format_explain_with_gap(
        venue_name="Anjuna Beach",
        block_type="venue",
        sources=sources,
        user_source_matches=[],
    )

    # Lockstep literal — §4.8 description matches this verbatim.
    assert "rationale wasn't captured" in text
    # Surfaces qek as the known limitation pointer.
    assert "qek" in text.lower()
    # Sources still render even on gap path.
    assert "https://reddit.com/r/IndiaTravel/anjuna" in text
    # Block metadata still surfaces.
    assert "Anjuna Beach" in text


def test_explain_block_not_found_routes_to_get_trip() -> None:
    """Parallel to format_alternative_block_not_found from slice 3.4a —
    distinct from trip-not-found because the trip exists.
    """
    from trip_mcp.tools._responses import format_explain_block_not_found

    block_id = uuid.uuid4()
    text = format_explain_block_not_found(trip_id=_TRIP_ID, block_id=block_id)
    assert str(_TRIP_ID) in text
    assert str(block_id) in text
    assert "get_trip" in text
    assert "block" in text.lower()


# ---------------------------------------------------------------------------
# Slice 3.5 commit 3: response formatters for share_trip + export_trip,
# plus the cross-formatter URL pin (load-bearing) — pins the /shared/{id}
# convention introduced in slice 3.5 against future refactors that might
# reintroduce the pre-3.5 broken /trips/{id} URL.
# ---------------------------------------------------------------------------


def test_share_url_helper_uses_shared_prefix_not_trips_prefix() -> None:
    """Cross-formatter URL pin 1/3 — _share_url is the single source of truth.

    Pre-3.5 convention was https://tripconcierge.app/trips/{id} which
    pointed at an auth-protected endpoint (broken share UX). Slice 3.5
    introduced /shared/{id} (unauth viewer endpoint, routes/shared.py).

    Pin the helper. Future refactors that reintroduce /trips/{id} break
    this test deliberately.
    """
    from trip_mcp.tools._responses import _share_url

    url = _share_url(_TRIP_ID)
    assert url.startswith("https://tripconcierge.app/shared/")
    assert "/trips/" not in url
    assert str(_TRIP_ID) in url


def test_created_trip_and_share_succeeded_use_identical_url_convention() -> None:
    """Cross-formatter URL pin 2/3 — sister formatters must agree.

    Drift between format_created_trip and format_share_succeeded is the
    regression class this test guards. Both formatters take share_url as
    a parameter; this test pins that callers pass URLs from the same
    _share_url helper, and that the resulting rendered text contains
    /shared/ (not /trips/) on both paths.
    """
    from trip_mcp.tools._responses import (
        _share_url,
        format_created_trip,
        format_share_succeeded,
    )

    url = _share_url(_TRIP_ID)
    created_text = format_created_trip(
        trip_id=_TRIP_ID,
        destination="Goa",
        budget_total=None,
        currency="USD",
        share_url=url,
    )
    share_text = format_share_succeeded(
        trip_id=_TRIP_ID,
        destination="Goa",
        share_url=url,
    )

    assert "/shared/" in created_text
    assert "/shared/" in share_text
    assert "/trips/" not in created_text
    assert "/trips/" not in share_text


def test_share_succeeded_includes_no_revocation_promise_v1_0a_privacy_model() -> None:
    """v1.0a privacy model is share-by-URL with no per-link revocation.
    The formatter MUST tell the user honestly — pinning so a future
    refactor doesn't drift toward implying revocation that we don't
    actually support yet. Tracked as trip-concierge-gid for v1.0b.
    """
    from trip_mcp.tools._responses import _share_url, format_share_succeeded

    text = format_share_succeeded(
        trip_id=_TRIP_ID, destination="Goa", share_url=_share_url(_TRIP_ID)
    )
    lower = text.lower()
    # Some honest framing about un-revocability.
    assert "doesn't expire" in lower or "doesn't support revoking" in lower or ("v1.0" in lower)
    # Must NOT promise anything we can't deliver.
    assert "you can revoke" not in lower
    assert "you can delete" not in lower or "delete the trip" in lower


def test_share_succeeded_falls_back_to_generic_message_when_destination_is_none() -> None:
    """Honest-broken at the formatter layer (slice 3.5 push-back from
    end-of-slice review). When the LLM doesn't know the destination
    (e.g., user said 'share my trip' without prior get_trip context),
    destination=None must render a generic-but-correct share message —
    NOT inject a literal "None" string or "your None trip" wording.

    Pins the LLM-orchestrator pattern: pure-function tools accept
    context from prior turns, fall back gracefully when context is
    absent. Same shape as Option C for state (slice 3.5 design).
    """
    from trip_mcp.tools._responses import _share_url, format_share_succeeded

    url = _share_url(_TRIP_ID)
    text = format_share_succeeded(trip_id=_TRIP_ID, destination=None, share_url=url)

    # URL + trip_id still surface — the load-bearing content is intact.
    assert str(_TRIP_ID) in text
    assert url in text
    # No literal "None" leaks into user-facing text.
    assert "None" not in text
    # No "your None trip" wording slip.
    assert "your None" not in text
    # Generic-but-correct framing surfaces.
    lower = text.lower()
    assert "your trip" in lower or "share link for your trip" in lower


def test_share_not_ready_branches_on_state_matching_regenerate_day_pattern() -> None:
    """Corpus-consistency pin — state-aware branching mirrors
    format_regenerate_day_not_ready from slice 3.3.

    states: never_planned / queued / running → "still being planned"
    state: failed                            → "didn't complete"
    state: cancelled / other                 → "likely cancelled"
    """
    from trip_mcp.tools._responses import format_share_not_ready

    for in_progress in ("never_planned", "queued", "running"):
        text = format_share_not_ready(in_progress).lower()
        assert "still being planned" in text or "still planning" in text, (
            f"state={in_progress} should surface in-progress language; got {text!r}"
        )
        assert "get_trip" in text

    failed = format_share_not_ready("failed").lower()
    assert "didn't complete" in failed or "did not complete" in failed
    assert "create_trip" in failed or "refine_trip" in failed

    other = format_share_not_ready("cancelled").lower()
    assert "cancelled" in other or "start fresh" in other


def test_export_succeeded_markdown_renders_inline_with_separator() -> None:
    """Markdown content is inline because Markdown renders well in
    conversation. The `---` separator lets the LLM distinguish wrapper
    text from export content per slice 3.5 corpus design.
    """
    from trip_mcp.tools._responses import format_export_succeeded_markdown

    content = "# Goa, India\n\n## Day 1\nAnjuna Beach"
    text = format_export_succeeded_markdown(trip_id=_TRIP_ID, destination="Goa", content=content)
    assert "Goa" in text
    assert "Anjuna Beach" in text
    assert "---" in text
    # Some "paste this" framing so the user knows they can copy it.
    lower = text.lower()
    assert "paste" in lower or "copy" in lower


def test_export_succeeded_json_uses_opt_in_disclosure_not_inline() -> None:
    """JSON branch DOES NOT inline the JSON body (would be wall-of-braces
    in conversation per slice-opening Q3). Surfaces char_count + asks
    the user whether to see the full dump.
    """
    from trip_mcp.tools._responses import format_export_succeeded_json

    text = format_export_succeeded_json(trip_id=_TRIP_ID, char_count=3456)

    # char_count surfaces in some humanized form.
    assert "3,456" in text or "3456" in text
    # Opt-in disclosure language present.
    lower = text.lower()
    assert "want" in lower or "show" in lower or "dump" in lower
    # Trip id surfaces so the LLM keeps it in context for a follow-up.
    assert str(_TRIP_ID) in text


def test_export_failed_names_failure_with_reason() -> None:
    """Catch-all for non-2xx export responses. Names the trip id +
    reason; offers retry path. Mirrors format_alternative_failed cadence.
    """
    from trip_mcp.tools._responses import format_export_failed

    text = format_export_failed(trip_id=_TRIP_ID, reason="trip not found")
    assert str(_TRIP_ID) in text
    assert "trip not found" in text
    assert "couldn't" in text.lower() or "could not" in text.lower()
