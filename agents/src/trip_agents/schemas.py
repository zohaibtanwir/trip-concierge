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

from pydantic import BaseModel, ConfigDict, Field

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
