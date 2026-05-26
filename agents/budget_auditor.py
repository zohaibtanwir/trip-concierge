"""Budget Auditor agent.

Role / goal / backstory copied verbatim from agents/prompts.md §1.4 (post
slice-2.3 update). Edit prompts.md first if you need to change them, then
mirror here in the same commit — see .claude/rules/agent-code-style.md.

Operates as a final-pass surgeon: applies surgical cuts (remove block X,
swap block Y for a cheaper alternative, compress the schedule) and returns
the revised plan + verdict for THIS pass. The orchestrator in crew.py runs
the Auditor up to MAX_AUDIT_PASSES times; the LLM itself sees one pass at
a time and never tries to track them. allow_delegation=False enforces "no
round-trips to other agents".
"""

from __future__ import annotations

from crewai import Agent

from llm import build_llm
from tools.calculator import calculator_tool
from tools.currency_convert import currency_convert_tool

budget_auditor = Agent(
    role="Budget Auditor",
    goal=(
        "Review the proposed itinerary against the user's hard budget constraints "
        "and other limits (max walking distance, dietary, accessibility, no-go "
        "list). When a constraint is violated, apply surgical revisions directly: "
        "remove a block, swap a block for a cheaper alternative, or compress the "
        "schedule. Return the revised plan and an honest verdict for this pass. "
        "If revisions can't bring the plan within constraints, return approved=false "
        "with the closest feasible plan and an explanation of which constraint "
        "couldn't be honored and by how much."
    ),
    backstory=(
        "You are an adversarial reviewer. Your job is to break plans that don't "
        "hold up. You don't care about the team's feelings, you care about whether "
        "the user can actually afford and execute this trip. You are precise about "
        "numbers and you do the math. You don't hide costs in 'misc' lines. You "
        "respect that 'budget' means budget, and you'd rather present a cheaper "
        "honest plan than an expensive one wrapped in optimistic estimates."
    ),
    # No delegation — surgeon mode, not referee. crew.py owns the retry loop.
    allow_delegation=False,
    verbose=True,
    memory=False,  # Slice 5.3 wires per-user memory.
    tools=[calculator_tool, currency_convert_tool],
    llm=build_llm(),
)
