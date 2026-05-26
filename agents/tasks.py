"""Task definitions. One function per task — agent assignments here, prompts in prompts.md.

User-supplied strings (destination, vibe, etc.) are passed via CrewAI's
kickoff inputs and template variables — NEVER f-string-interpolated
into the task description. See .claude/rules/agent-code-style.md rule #8.
"""

from __future__ import annotations

from crewai import Task

from local_expert import local_expert
from logistics import logistics_planner
from researcher import researcher
from schemas import TripPlan


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
