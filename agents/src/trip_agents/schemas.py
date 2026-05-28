"""Pydantic schemas for crew output.

CrewAI's Task supports `output_pydantic=Schema` which forces the LLM
to produce JSON matching the schema. Much more robust than parsing
free-form text.

The schemas here mirror the eventual Day/Block DB models from
PRD §2.3, but with extra=allow so LLMs can include fields we don't
strictly require.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BlockType = Literal["venue", "transit", "meal", "rest"]


class Block(BaseModel):
    model_config = ConfigDict(extra="allow")

    order: int = Field(ge=1)
    type: BlockType
    venue_name: str = Field(min_length=1)
    start_time: str = ""
    duration_minutes: int = Field(ge=0)
    est_cost: float | None = None
    currency: str = "USD"
    source_urls: list[str] = Field(default_factory=list)


class Day(BaseModel):
    model_config = ConfigDict(extra="allow")

    day_number: int = Field(ge=1)
    date: str | None = None
    summary: str = ""
    blocks: list[Block] = Field(min_length=1)


class TripPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    days: list[Day] = Field(min_length=1)


class AuditedPlan(BaseModel):
    """Per-pass output from the Budget Auditor AND the final orchestrator return.

    Each Auditor pass produces an AuditedPlan with `revision_log` containing
    only that pass's entries. The orchestrator concatenates per-pass logs
    across passes with a "Pass N: " prefix on each entry.
    """

    model_config = ConfigDict(extra="allow")

    approved: bool
    days: list[Day] = Field(min_length=1)
    per_day_costs: list[float] = Field(default_factory=list)
    total_cost: float = 0.0
    currency: str = "USD"
    constraints_violated: list[str] = Field(default_factory=list)
    explanation: str = ""
    revision_log: list[str] = Field(default_factory=list)


class TripRunRequest(BaseModel):
    """Input shape for `crew.run()` / the agents service `POST /run` endpoint.

    Single source of truth — backend constructs this when enqueueing planning
    jobs (slice 2.5b); agents service validates incoming HTTP requests with it;
    crew.run() consumes it via `**req.model_dump(exclude_none=True)` so the
    DEFAULT_INPUTS dict in crew.py fills in the LLM-friendly "unspecified"
    strings for fields left out of the request.

    Field names match the template variables CrewAI substitutes into each
    Task description — change names here only by also updating the templates.
    """

    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1, max_length=200)
    start_date: str | None = None
    end_date: str | None = None
    group_size: int = Field(default=2, ge=1)
    budget_total: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    vibe: str = ""
    constraints: str = ""
    user_sources: str = ""
    pace: Literal["packed", "balanced", "lazy"] = "balanced"
    per_day_budget: float | None = Field(default=None, ge=0)
    dietary: str = ""
    mobility: str = ""
    no_go_list: str = ""
    max_walking_km: float | None = Field(default=None, ge=0)


class CreateTripInput(BaseModel):
    """Input shape for the create_trip MCP tool. Source of truth for both
    Pydantic runtime validation AND the JSON Schema emitted to Claude
    Desktop via model_json_schema().

    `destination` and `vibe` are individually Optional at the field level,
    but the model_validator below enforces "at least one of the two." The
    JSON Schema cannot express that cross-field rule natively — the LLM
    learns it from the per-field descriptions plus this docstring (which
    surfaces as the schema's top-level `description`).

    Distinct from TripRunRequest: this is what the LLM extracts from user
    speech (MCP boundary). TripRunRequest is what the agents worker
    consumes (queue boundary), with structured constraint fields the chat
    user wouldn't naturally mention. The MCP tool translates the former
    into the latter when issuing POST /trips and POST /trips/{id}/plan.
    """

    model_config = ConfigDict(extra="forbid")

    destination: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Where the user wants to go. Required if no vibe is provided. "
            "Extract the named place from the user's request — city, region, "
            "country, neighborhood, all fine."
        ),
    )
    start_date: str | None = Field(
        default=None,
        description=(
            "Trip start date in YYYY-MM-DD format. Leave unset if the user "
            "didn't give specific dates; do not invent or assume."
        ),
    )
    end_date: str | None = Field(
        default=None,
        description=(
            "Trip end date in YYYY-MM-DD format. Leave unset if the user "
            "didn't give specific dates; do not invent or assume."
        ),
    )
    group_size: int = Field(
        default=1,
        ge=1,
        description=(
            "Number of travelers. Extract from phrases like 'me and my partner' "
            "(2), 'group of 5', 'solo trip' (1). Defaults to 1."
        ),
    )
    budget_total: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Total trip budget as a number (e.g., 40000 for ₹40k, 2500 for "
            "$2500). Leave unset if the user didn't mention a budget — do not "
            "invent one."
        ),
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description=(
            "ISO-4217 currency code: USD, INR, EUR, GBP, JPY, etc. Extract "
            "from the budget's symbol or context. Defaults to USD."
        ),
    )
    pace: Literal["packed", "balanced", "lazy"] = Field(
        default="balanced",
        description=(
            "How packed the days are: 'packed' = max sights and activities, "
            "'balanced' = mix of activity and rest (default), 'lazy' = low-key, "
            "lots of downtime. Extract from words like 'relaxed' (lazy), "
            "'easy' (lazy), 'busy' (packed), 'pack it in' (packed)."
        ),
    )
    vibe: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Short phrase describing the trip's feel — extract user words like "
            "'chill', 'adventure', 'foodie', 'romantic', 'family-friendly'. "
            "Leave unset if no vibe was mentioned. Required if destination is "
            "not provided."
        ),
    )

    @model_validator(mode="after")
    def _at_least_destination_or_vibe(self) -> CreateTripInput:
        if not self.destination and not self.vibe:
            raise ValueError("at least one of `destination` or `vibe` must be provided")
        return self


class GetTripInput(BaseModel):
    """Input for the get_trip MCP tool — single field, trip_id only."""

    model_config = ConfigDict(extra="forbid")

    trip_id: str = Field(
        description=(
            "The trip's UUID. Returned by create_trip and mentioned earlier in "
            "the conversation. Required."
        ),
    )


class RefineTripInput(BaseModel):
    """Input for the refine_trip MCP tool — modifications to an existing trip."""

    model_config = ConfigDict(extra="forbid")

    trip_id: str = Field(description="The trip's UUID to refine.")
    refinement_description: str = Field(
        min_length=10,
        max_length=2000,
        description=(
            "Free-text instruction for what to change. Examples: 'make Day 2 "
            "chiller', 'we're vegetarian, swap food picks', 'I want to spend "
            "less on Day 3', 'redo the whole trip with a less packed pace'. "
            "Extract the user's intent verbatim if possible — don't paraphrase."
        ),
    )


class RegenerateDayInput(BaseModel):
    """Input for the regenerate_day MCP tool — replan one specific day."""

    model_config = ConfigDict(extra="forbid")

    trip_id: str = Field(description="The trip's UUID.")
    day_number: int = Field(
        ge=1,
        le=30,
        description=(
            "Which day of the trip to regenerate (1-indexed). Extract from "
            "phrases like 'redo Day 2', 'change the third day', 'Day 5 isn't "
            "working'."
        ),
    )
    hint: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional free-text guidance for the regeneration — e.g., 'more "
            "food, less hiking', 'cheaper venues', 'rainy-day options'. "
            "Leave unset if the user didn't give a specific hint."
        ),
    )


class AddConstraintInput(BaseModel):
    """Input for the add_constraint MCP tool — slice 3.4a commit 5.

    Mirrors backend AddConstraintRequest (app/routes/constraints.py). The
    backend re-validates; this schema is what Claude Desktop reads to
    populate fields.
    """

    model_config = ConfigDict(extra="forbid")

    trip_id: str = Field(description="The trip's UUID.")
    constraint_text: str = Field(
        min_length=3,
        max_length=500,
        description=(
            "Free-text statement of the constraint, verbatim from the user. "
            'Examples: "I\'m vegetarian", "no nightclubs", "₹3000/day '
            'cap", "we can\'t walk more than 5km in a day". Extract the '
            "user's wording — don't paraphrase. Used both as the dedup key "
            "and as the prompt-facing language."
        ),
    )
    constraint_kind: str = Field(
        default="custom",
        description=(
            "One of: budget, dietary, mobility, no_go, walking_limit, "
            "custom. Pick the closest fit; default 'custom' if uncertain. "
            "Examples: 'I'm vegetarian' → dietary, 'no nightclubs' → "
            "no_go, '₹3000/day cap' → budget, 'we can't walk more than "
            "5km' → walking_limit, 'home before midnight' → custom."
        ),
    )


class FindAlternativeInput(BaseModel):
    """Input for the find_alternative MCP tool — slice 3.4a commit 5.

    block_id MUST come from a real trip's data (get_trip). The
    description here is one half of the layered UUID-hallucination
    defense; the task prompt (§3.7) is the other half. See the
    "Why 'Do NOT generate UUIDs' twice" rationale in agents/prompts.md.
    """

    model_config = ConfigDict(extra="forbid")

    trip_id: str = Field(description="The trip's UUID.")
    block_id: str = Field(
        description=(
            "The UUID of the specific block to replace. MUST be a real "
            "block_id from the trip's data — get it from get_trip's "
            "output. DO NOT synthesize a UUID-shaped string from "
            "context, prior turns, or your own generation; if you don't "
            "have a real block_id, call get_trip first. The backend "
            "rejects (404) any block_id not on this trip."
        ),
    )
    reason: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Optional short free-text reason for the swap — e.g., 'closed "
            "for renovations', 'too expensive', 'bad reviews'. Helps the "
            "ranking but is not required. Leave unset if the user didn't "
            "give a specific reason."
        ),
    )


class Alternative(BaseModel):
    """One ranked alternative venue produced by find_alternative.

    Slice 3.4a commit 3. Per agents/prompts.md §3.7, the Researcher is
    instructed to produce real venues with citations — `source_urls`
    non-empty + a substantive `rationale` are the load-bearing fields
    that distinguish a real recommendation from a fabrication.
    """

    model_config = ConfigDict(extra="allow")

    venue_name: str = Field(min_length=1)
    type: Literal["venue", "meal", "activity", "transit", "rest"]
    duration_minutes: int = Field(gt=0)
    est_cost: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    source_urls: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=10)


class AlternativesList(BaseModel):
    """find_alternative output — exactly 3 ranked alternatives.

    The min_length=max_length=3 constraint is the load-bearing schema-layer
    enforcement of §3.7's "Return exactly 3 alternatives" instruction.
    If the crew drifts to 2 or 4 items, output_pydantic validation fails
    and crew.find_alternative raises a clear error rather than silently
    returning degraded output.

    Belt and suspenders against LLM drift:
    1. Task prompt (§3.7) says "Return exactly 3 alternatives".
    2. AlternativesList schema enforces it via Field(min_length=3, max_length=3).
    3. _extract_alternatives_list helper in crew.py surfaces the failure.
    """

    model_config = ConfigDict(extra="forbid")

    alternatives: list[Alternative] = Field(min_length=3, max_length=3)
