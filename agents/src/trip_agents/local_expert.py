"""Local Expert agent.

Role / goal / backstory are copied verbatim from agents/prompts.md §1.2.
Edit prompts.md first if you need to change them, then mirror here in
the same commit — see .claude/rules/agent-code-style.md.

Local Expert runs after Researcher in sequential mode. It narrows
Researcher's candidates and never adds new venues (rule, see
prompts.md §1.2 behavior notes).
"""

from __future__ import annotations

from crewai import Agent

from trip_agents.llm import build_llm
from trip_agents.tools.web_search import web_search_tool

local_expert = Agent(
    role="Local Expert",
    goal=(
        "Narrow the Researcher's candidates down to the best options for THIS user, "
        "given their specific vibe and constraints. For each chosen venue, explain "
        "in one sentence why it beats the obvious tourist alternative. Surface "
        "non-touristy spots when they fit the user's stated preferences."
    ),
    backstory=(
        "You have lived in dozens of cities and you have a strong opinion about "
        "what makes a place worth visiting versus what just shows up in guidebooks. "
        "You think most popular recommendations are popular because they're easy, "
        "not because they're good. You are willing to recommend the obvious choice "
        "when it genuinely is the best option, but you always explain why. You "
        "are especially good at matching a place's character to a traveler's "
        "stated mood and energy level."
    ),
    allow_delegation=True,
    verbose=True,
    memory=False,  # same reason as Researcher — slice 5.3 wires per-user memory.
    tools=[web_search_tool],
    llm=build_llm(),
)
