"""Task definitions. One function per task — agent assignments here, prompts in prompts.md.

User-supplied strings (destination, vibe, etc.) are passed via CrewAI's
kickoff inputs and template variables — NEVER f-string-interpolated
into the task description. See .claude/rules/agent-code-style.md rule #8.
"""

from __future__ import annotations

from crewai import Task

from trip_agents.budget_auditor import budget_auditor
from trip_agents.local_expert import local_expert
from trip_agents.logistics import logistics_planner
from trip_agents.researcher import researcher
from trip_agents.schemas import AlternativesList, AuditedPlan, Day, TripPlan


def make_research_task() -> Task:
    """Initial venue research. Description and expected_output are the canonical
    strings from agents/prompts.md §3.1 (edit there first, mirror here).
    """
    return Task(
        description=(
            "The user wants a trip to {destination} from {start_date} to {end_date} "
            "for a group of {group_size}. Their budget is {budget_total} {currency}. "
            "Their stated vibe: '{vibe}'. Additional constraints: {constraints}. "
            "BYO research the user has attached: {user_sources}.\n\n"
            "Find 3-5 candidate venues for each of: places to stay, things to do, "
            "places to eat. Every candidate MUST include a source URL and a one-line "
            "rationale. If user_sources contain relevant matches, prioritize them and "
            "tag them with 'from_user_source: true'."
        ),
        agent=researcher,
        expected_output=(
            "JSON with three arrays: stays, activities, meals. Each item has: "
            "name, brief_description, source_urls (list), rationale, "
            "from_user_source (bool), estimated_cost, currency."
        ),
    )


def make_local_expertise_task(research: Task) -> Task:
    """Narrow the Researcher's candidates. Description and expected_output
    are the canonical strings from agents/prompts.md §3.2.
    """
    return Task(
        description=(
            "Review the Researcher's candidates. Narrow each category to the best "
            "options for this specific user given their vibe '{vibe}' and constraints. "
            "For each chosen item, add a 'why_this_not_that' sentence explaining why "
            "this beats a more obvious tourist alternative. Do not add new venues."
        ),
        agent=local_expert,
        context=[research],
        expected_output=(
            "Same JSON structure as research_task, narrowed and with a "
            "'why_this_not_that' field added to each item."
        ),
    )


def make_planning_task(expertise: Task) -> Task:
    """Build the day-by-day itinerary. Description and expected_output are
    the canonical strings from agents/prompts.md §3.3.
    """
    return Task(
        description=(
            "Build a day-by-day itinerary from the chosen venues. Respect the user's "
            "pace setting ({pace}: packed/balanced/lazy). Group geographically close "
            "venues into the same day. Include realistic travel times between blocks. "
            "Account for opening hours and day-of-week closures. Insert meal breaks "
            "at sensible times."
        ),
        agent=logistics_planner,
        context=[expertise],
        expected_output=(
            "JSON with a 'days' array. Each day has: day_number, date, summary, and "
            "an ordered 'blocks' array. Each block has: order, type "
            "(venue|transit|meal|rest), venue_name, start_time, duration_minutes, "
            "est_cost, currency, source_urls."
        ),
        # CrewAI enforces this schema on the final output: the LLM is forced to
        # return JSON matching TripPlan, no prose preamble.
        output_pydantic=TripPlan,
    )


def make_audit_task() -> Task:
    """One pass of the audit loop. Invoked outside the main Crew — the plan
    to audit comes in via the {current_plan_json} template var, not via
    CrewAI's context= mechanism. Description + expected_output are verbatim
    from agents/prompts.md §3.4 (post slice-2.3 update).
    """
    return Task(
        description=(
            "Audit the itinerary against the user's hard constraints: "
            "total_budget={budget_total} {currency}, per_day_budget={per_day_budget}, "
            "dietary={dietary}, mobility={mobility}, no_go={no_go_list}, "
            "max_walking_km_per_day={max_walking_km}.\n\n"
            "Current itinerary to audit (JSON):\n{current_plan_json}\n\n"
            "When any constraint is violated, apply surgical revisions directly: "
            "remove or swap individual blocks, compress days, or cut optional stops. "
            "Return the revised plan and your verdict for THIS pass. Do not delegate. "
            "Do not try to run multiple passes yourself — the orchestrator re-invokes "
            "you with your revised plan if approved=false, up to a system-level cap. "
            "Focus on doing one good pass and reporting honestly."
        ),
        agent=budget_auditor,
        expected_output=(
            "JSON with: approved (bool, true iff plan now satisfies ALL constraints), "
            "days (array — same shape as planning_task output, with this pass's "
            "revisions applied), per_day_costs (numbers indexed by day), total_cost "
            "(number), currency (string), constraints_violated (list, empty if "
            "approved=true), explanation (string, non-empty only if approved=false), "
            "revision_log (list of human-readable strings describing what THIS pass "
            "cut/swapped/compressed and why)."
        ),
        output_pydantic=AuditedPlan,
    )


def make_refine_task() -> Task:
    """Hierarchical refine task — slice 3.3. Description + expected_output
    are the canonical strings from agents/prompts.md §3.5 (rewritten in
    commit 4 to drop diff_summary in favor of AuditedPlan shape).
    """
    return Task(
        description=(
            "The user has an existing trip and wants to modify it. Current trip "
            "state (JSON): {trip_state_json}.\n\n"
            "User instruction: '{refinement_description}'.\n\n"
            "Decide which agents to route this through, apply the modification, "
            "and produce an updated full itinerary. Preserve any blocks marked "
            "locked=true. Validate the result against the trip's stated budget "
            "and constraints — invoke Budget Auditor as the final step and "
            "return whatever it produces (approved or not). The orchestrator "
            "(crew.py) runs Budget Auditor again up to MAX_REFINE_AUDIT_PASSES "
            "times if approved=false — do not loop internally trying to satisfy "
            "it. Focus on one good refine pass."
        ),
        expected_output=(
            "JSON matching the AuditedPlan schema: approved (bool), days (array), "
            "per_day_costs (numbers indexed by day), total_cost (number), "
            "currency (string), constraints_violated (list, empty if approved=true), "
            "explanation (string, non-empty only if approved=false), "
            "revision_log (list of human-readable strings describing what changed)."
        ),
        # No agent= because hierarchical mode routes via manager_llm.
        output_pydantic=AuditedPlan,
    )


def make_regenerate_day_task() -> Task:
    """Sequential single-day regenerate task — slice 3.3. Description and
    expected_output are the canonical strings from agents/prompts.md §3.X
    (new section added in commit 4).
    """
    return Task(
        description=(
            "Regenerate blocks for one specific day of an existing trip.\n\n"
            "Trip context (destination, currency, etc.): {trip_context_json}.\n"
            "Target day to regenerate: {target_day_json}.\n"
            "Blocks at these positions are LOCKED and must not appear in your "
            "output — the worker will splice them back in: {locked_blocks_json}.\n"
            "Produce new blocks ONLY for these positions: {unlocked_positions}.\n\n"
            "Optional user hint for the regen: {hint}.\n\n"
            "Return a single Day object whose blocks list contains exactly the "
            "blocks for the unlocked positions — same order field values as "
            "the listed positions. Day-level fields (day_number, date, summary) "
            "echo the input."
        ),
        expected_output=(
            "JSON matching the Day schema: day_number (int), date (string|null), "
            "summary (string), blocks (array — one Block per unlocked position, "
            "each with order, type, venue_name, duration_minutes, currency, and "
            "source_urls)."
        ),
        agent=logistics_planner,
        output_pydantic=Day,
    )


def make_find_alternative_task() -> Task:
    """Sequential single-agent task for find_alternative — slice 3.4a.

    Description and expected_output are the canonical strings from
    agents/prompts.md §3.7 (added in slice 3.4a commit 3 alongside
    this source per agent-code-style.md rule 1).

    Researcher alone (Option B from the file-tree session) — tracked as
    trip-concierge-5yw for Local Expert addition reassessment after
    Claude Desktop validation.
    """
    return Task(
        description=(
            "The user wants to replace one specific block in their existing "
            "trip. Produce 3 alternatives that fit the trip's context and "
            "constraints.\n\n"
            "Trip context: destination={destination}, currency={currency}.\n"
            "Block to replace: type={block_type}, original "
            "venue={block_venue_name}, duration={block_duration_minutes} "
            "minutes, slot time={block_start_time}.\n"
            "User's reason for swap (may be empty): {reason}.\n"
            "Trip constraints to respect (rank alternatives by fit to "
            "these): {constraints_summary}.\n\n"
            "Return exactly 3 alternatives, ranked by fit (best first). "
            "For each: venue_name, type (same as the block being replaced "
            "— venue/meal/activity/transit/rest), an estimated "
            "duration_minutes (close to the original block's duration is "
            "best), est_cost in {currency}, source_urls (at least one), "
            "and a one-line rationale explaining why this venue fits this "
            "user given the listed constraints.\n\n"
            "Do NOT generate UUIDs, block IDs, or any IDs in your output "
            "— those are handled by the caller. Focus your effort on real "
            "venue research (Tavily search is enabled) and ranking. If you "
            "cite a venue, you MUST have a source URL for it; do not "
            "invent venues you can't cite."
        ),
        agent=researcher,
        expected_output=(
            "JSON matching the AlternativesList schema: an `alternatives` "
            "array of exactly 3 items. Each item has: venue_name (string), "
            "type (one of venue|meal|activity|transit|rest, matching the "
            "block being replaced), duration_minutes (integer, close to "
            "the original block's duration), est_cost (number), currency "
            "(3-letter ISO code), source_urls (non-empty array of URLs), "
            "rationale (short string explaining the fit). Do NOT include "
            "any UUIDs or block_ids."
        ),
        output_pydantic=AlternativesList,
    )
