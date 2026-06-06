"""Synthesize the refinement_description for an add_constraint enqueue.

Slice 3.4a commit 2. add_constraint reuses the slice-3.3 refine_trip arq
task; the route synthesizes a refinement_description that crosses the
route → worker → crew boundary (interpolated as `{refinement_description}`
in refine_task per agents/prompts.md §3.5).

Three load-bearing properties:
1. **Deterministic.** Same (kind, value, raw_text) triplet → byte-identical
   output. No timestamps, no random IDs. Required for reproducible debugging:
   replaying a constraint via SQL must regenerate the same prompt.
2. **Per-kind framing.** Each kind has its own semantic prose so the crew
   reads the constraint's meaning (a budget cap vs a dietary restriction
   vs a walking limit) without parsing key=value tags.
3. **Merge semantics.** Names the anti-replacement invariant explicitly —
   the new constraint is IN ADDITION to existing constraints, the crew
   must NOT relax prior constraints, and the Auditor verifies the UNION
   holds. Without this, the hierarchical manager_llm might drift on
   merge-vs-replace semantics.

Per-tool prohibition discipline: same pattern as the slice-3.2 "DO NOT
fabricate venues" guidance — name the forbidden behavior at the prompt
layer, don't rely on the LLM defaulting correctly.
"""

from __future__ import annotations

from typing import Any


def _framing_for_kind(kind: str, value: Any) -> str:
    """Per-kind natural-language framing of the new constraint."""
    if kind == "dietary":
        return f"Apply this dietary constraint across the trip: {value}."
    if kind == "budget":
        return f"Apply a new per-day budget cap of {value} (trip currency)."
    if kind == "mobility":
        return f"Apply this mobility constraint across the trip: {value}."
    if kind == "no_go":
        return f"Exclude this from the trip: {value}."
    if kind == "walking_limit":
        return f"Apply a daily walking limit of {value} km."
    if kind == "accessibility":
        return f"Apply this accessibility requirement across the trip: {value}."
    # custom or unrecognized — fall through to generic framing.
    return f"Apply this user-stated constraint: {value}."


def synthesize_constraint_refinement(*, kind: str, value: Any, raw_text: str) -> str:
    """Build the refinement_description for the refine_trip task.

    The output is interpolated into agents/prompts.md §3.5's
    `User instruction: '{refinement_description}'.` slot.
    """
    framing = _framing_for_kind(kind, value)
    return (
        f"The user added a new constraint. {framing} "
        f"This is IN ADDITION to the trip's existing constraints "
        f"(see trip state); do not relax any prior constraints. "
        f'Their original wording: "{raw_text}". '
        f"Update any blocks that violate this constraint; preserve "
        f"blocks that already comply with this AND all prior "
        f"constraints. The Budget Auditor must confirm the result "
        f"satisfies ALL constraints (existing + new) before returning."
    )
