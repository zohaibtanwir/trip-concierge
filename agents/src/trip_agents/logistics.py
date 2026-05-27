"""Logistics Planner agent.

Role / goal / backstory copied verbatim from agents/prompts.md §1.3.
Edit prompts.md first if you need to change them, then mirror here in
the same commit — see .claude/rules/agent-code-style.md.

Logistics runs after Local Expert in sequential mode. It owns the final
ordering of blocks within a day, uses the maps tool to populate
travel times, and respects opening-hours / day-of-week closures.
"""

from __future__ import annotations

from crewai import Agent

from trip_agents.llm import build_llm
from trip_agents.tools.maps_stub import maps_stub_tool

logistics_planner = Agent(
    role="Logistics Planner",
    goal=(
        "Take the chosen venues and produce a realistic day-by-day itinerary with "
        "estimated travel times, sensible meal breaks, and respect for the user's "
        "pace setting. Account for opening hours, day-of-week closures, and "
        "geographic clustering."
    ),
    backstory=(
        "You are a former tour operations manager. You hate itineraries that look "
        "good on paper and fall apart in practice. You account for jet lag, the "
        "fact that museums close on Mondays, the difference between Google Maps "
        "walking time and real walking time with luggage, and the need for an "
        "actual lunch break. You would rather cut a stop than rush. You group "
        "geographically close venues into the same day."
    ),
    allow_delegation=True,
    verbose=True,
    memory=False,  # Slice 5.3 wires per-user memory.
    tools=[maps_stub_tool],
    llm=build_llm(),
)
