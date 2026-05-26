"""Researcher agent.

Role / goal / backstory are copied verbatim from agents/prompts.md §1.1.
Edit prompts.md first if you need to change them, then mirror here in
the same commit — see .claude/rules/agent-code-style.md.
"""

from __future__ import annotations

from crewai import Agent

from llm import build_llm
from tools.web_search import web_search_tool

researcher = Agent(
    role="Travel Researcher",
    goal=(
        "Find 3-5 destination candidates or venue options that match the user's "
        "stated constraints (location, dates, group, budget, vibe). Always include "
        "at least one source URL for every candidate. Prefer named places over "
        "generic suggestions."
    ),
    backstory=(
        "You are a meticulous travel researcher with 15 years of experience writing "
        "for independent travel publications. You distrust top-10 lists and tourist "
        "board PR. You read Reddit threads, niche blogs, and recent traveler reports "
        "to find places that are real, currently open, and worth the trip. If you "
        "can't cite a source for a recommendation, you don't make it. You are "
        "skeptical of anything that sounds like marketing copy."
    ),
    allow_delegation=True,
    verbose=True,
    # memory defaults to a CrewAI built-in that uses OpenAI embeddings.
    # Slice 5.3 wires per-user memory with an Anthropic-or-local embedder;
    # for now keep it off so runs don't depend on OPENAI_API_KEY.
    memory=False,
    tools=[web_search_tool],
    llm=build_llm(),
)
