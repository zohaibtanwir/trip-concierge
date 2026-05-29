# Agent Prompts and MCP Tool Descriptions

**This file is version-controlled. Any change to agent role/goal/backstory or MCP tool description must be made here first, then in the Python source.**

The prompts below are the canonical strings. Copy-paste into the Python source; do not paraphrase.

---

## 1. CrewAI Agents

### 1.1 Researcher

```python
from crewai import Agent

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
    memory=True,
    tools=[web_search_tool, web_scrape_tool, user_sources_search_tool],
)
```

**Behavior notes:**
- Researcher is the only agent that calls external web search. Others ask Researcher via delegation if they need fresh data.
- Every output must include a `sources` field with at least one URL per candidate.
- If the user has attached BYO research (via `add_source`), Researcher must check it first and prioritize matches.

### 1.2 Local Expert

```python
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
    memory=True,
    tools=[reviews_aggregator_tool, web_search_tool],
)
```

**Behavior notes:**
- Local Expert never adds new venues that Researcher didn't surface. It only narrows and explains.
- The "why this not that" sentence is mandatory and gets shown in the UI.

### 1.3 Logistics Planner

```python
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
    memory=True,
    tools=[maps_api_tool, calendar_math_tool],
)
```

**Behavior notes:**
- Logistics owns the final ordering of blocks within a day.
- Travel times between blocks must be populated, not estimated as "short walk".
- Day-of-week opening hours must be checked for any venue with limited days.

### 1.4 Budget Auditor

```python
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
    allow_delegation=False,
    verbose=True,
    memory=True,
    tools=[calculator_tool, currency_convert_tool],
)
```

**Behavior notes:**
- Budget Auditor runs last in sequential mode. In hierarchical mode (refine_task) it's one of the four agents the manager_llm can route to; the manager is responsible for invoking it as the final check before returning, and the refine_task's expected_output forces the result through `AuditedPlan` so audit fields can't be skipped.
- **Surgeon, not referee.** The Auditor applies its own cuts (remove/swap blocks, compress days) instead of round-tripping back to Logistics. allow_delegation=False enforces this.
- **Orchestrator owns the loop, not the LLM.** crew.py invokes the Auditor with a fresh single-pass task up to `MAX_AUDIT_PASSES` times. If a pass returns approved=true, the orchestrator returns immediately. Otherwise that pass's revised plan feeds the next pass. After the cap, whatever the last pass produced is the final return (approved or not). The Auditor itself sees ONE pass at a time and never tries to track them. The infeasibility return is the expected output for infeasible asks, not an error.
- Output must include a per-day cost breakdown, a total, and a revision_log describing what THIS pass cut/swapped and why. The orchestrator concatenates per-pass logs with a "Pass N: " prefix.

---

## 2. Crew composition

```python
from crewai import Crew, Process

def build_crew(process: Process = Process.sequential) -> Crew:
    if process == Process.sequential:
        return Crew(
            agents=[researcher, local_expert, logistics_planner, budget_auditor],
            tasks=[
                research_task,
                local_expertise_task,
                planning_task,
                audit_task,
            ],
            process=Process.sequential,
            memory=True,
            verbose=True,
        )
    elif process == Process.hierarchical:
        return Crew(
            agents=[researcher, local_expert, logistics_planner, budget_auditor],
            tasks=[refine_task],  # single high-level task; manager routes
            process=Process.hierarchical,
            manager_llm="claude-sonnet-4",
            memory=True,
            verbose=True,
        )
```

**When to use each process:**
- `Process.sequential` — initial trip generation. Predictable, faster, cheaper.
- `Process.hierarchical` — `refine_trip` calls, mid-trip replans, any case where the user's instruction doesn't map cleanly to a single agent.

---

## 3. Task definitions

### 3.1 research_task

```python
research_task = Task(
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
```

### 3.2 local_expertise_task

```python
local_expertise_task = Task(
    description=(
        "Review the Researcher's candidates. Narrow each category to the best "
        "options for this specific user given their vibe '{vibe}' and constraints. "
        "For each chosen item, add a 'why_this_not_that' sentence explaining why "
        "this beats a more obvious tourist alternative. Do not add new venues."
    ),
    agent=local_expert,
    context=[research_task],
    expected_output=(
        "Same JSON structure as research_task, narrowed and with a "
        "'why_this_not_that' field added to each item."
    ),
)
```

### 3.3 planning_task

```python
planning_task = Task(
    description=(
        "Build a day-by-day itinerary from the chosen venues. Respect the user's "
        "pace setting ({pace}: packed/balanced/lazy). Group geographically close "
        "venues into the same day. Include realistic travel times between blocks. "
        "Account for opening hours and day-of-week closures. Insert meal breaks "
        "at sensible times."
    ),
    agent=logistics_planner,
    context=[local_expertise_task],
    expected_output=(
        "JSON with a 'days' array. Each day has: day_number, date, summary, and "
        "an ordered 'blocks' array. Each block has: order, type "
        "(venue|transit|meal|rest), venue_name, start_time, duration_minutes, "
        "est_cost, currency, source_urls."
    ),
)
```

### 3.4 audit_task

```python
audit_task = Task(
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
    # No context= — the audit task runs outside the main Crew, with the plan
    # passed in via the {current_plan_json} template var.
    expected_output=(
        "JSON with: approved (bool, true iff plan now satisfies ALL constraints), "
        "days (array — same shape as planning_task output, with this pass's "
        "revisions applied), per_day_costs (numbers indexed by day), total_cost "
        "(number), currency (string), constraints_violated (list, empty if "
        "approved=true), explanation (string, non-empty only if approved=false), "
        "revision_log (list of human-readable strings describing what THIS pass "
        "cut/swapped/compressed and why)."
    ),
)
```

### 3.5 refine_task (hierarchical)

```python
refine_task = Task(
    description=(
        "The user has an existing trip and wants to modify it. Current trip "
        "state (JSON): {trip_state_json}.\n\n"
        "User instruction: '{refinement_description}'.\n\n"
        "Decide which agents to route this through, apply the modification, "
        "and produce an updated full itinerary. Preserve any blocks marked "
        "locked=true. Validate the result against the trip's stated budget "
        "and constraints — Budget Auditor must approve before returning."
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
```

**Why AuditedPlan and not a separate RefinedPlan + diff_summary shape:**

Slice 3.3 commit 4 (2026-05-28) chose the AuditedPlan output for refine over a richer `updated_trip + diff_summary + agents_consulted` envelope. Reasons:

- **Persistence symmetry.** `persist_audited_plan` consumes AuditedPlan unchanged — no new persistence function for refine. Halves the schema surface and means the same destructive-replace semantics apply to plan_trip and refine_trip alike.
- **Audit must be the final gate, not optional polish.** Forcing the manager_llm through an AuditedPlan-shaped expected_output makes "Budget Auditor approves the result" structurally required. A `diff_summary` envelope made the audit feel optional in early drafts.
- **diff_summary belongs at the surfacing layer, not the crew layer.** The MCP `get_trip` tool produces a conversational diff naturally when the user asks "what changed?" — the LLM compares before/after observations on the trip. The PWA in Phase 4 will want a structured server-side diff (tracked as `trip-concierge-dsj`).

The fields dropped from the old expected_output (`updated_trip`, `diff_summary`, `agents_consulted`) all have equivalents reachable from other sources: `updated_trip` = the days array, `diff_summary` = conversational LLM-text in the MCP layer, `agents_consulted` = the Langfuse trace.

### 3.6 regenerate_day_task

```python
regenerate_day_task = Task(
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
```

**Why locked blocks are EXCLUDED from the crew's output, not just flagged as preserved:**

Slice 3.3 commit 4 chose option (a) for locked-block handling: pre-filter in the worker, splice deterministically afterward. The crew never sees locked blocks in its output schema. Reasons:

- **The LLM cannot accidentally drop or modify what it cannot generate.** A "preserve blocks marked locked=true in your output" instruction is a soft constraint the model can violate. Excluding locked positions from `unlocked_positions` and refusing to include them in the expected_output is a hard constraint enforced by the worker.
- **Same principle as `MAX_AUDIT_PASSES` enforced in Python, not in a prompt.** The audit loop limit is a code invariant; locked-block preservation is now too.
- **Deterministic splice is auditable.** The worker's splice path (`spliced = sorted(regen_blocks + locked_block_dicts, key=order)`) is one line of Python that can be unit-tested. A model-honor approach can't be tested deterministically.

The crew DOES receive `locked_blocks` as read-only context so it can plan around them sensibly (e.g., don't propose a 4-hour meal block adjacent to a locked 4-hour activity), but those blocks never round-trip through the output.

---

### 3.7 find_alternative_task

```python
find_alternative_task = Task(
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
```

**Why Researcher alone (not Local Expert too):**

Slice 3.4a chose Option B (Researcher-alone, single-agent `Process.sequential`) over Option A (Researcher → Local Expert, two-agent sequential). The decision criteria were wall-time variance under the slice's 90s sync-route timeout and the size of the task.

- **Wall-time budget.** find_alternative runs synchronously inside an MCP request — the 90s timeout is a hard ceiling, not a soft target. Each additional crew agent adds an LLM hop (~10-25s p50, longer p99 with tool calls). A two-agent chain that p99s past 90s would tail-cut the user's MCP turn. Researcher-alone keeps the worst-case bounded.
- **Task surface area.** find_alternative is "3 venues that fit constraints" — narrower than the full initial-generation flow where Local Expert's "why this, not that" reasoning earns its keep against tourist-trap selection. For one swap, the marginal quality from a second pass is small; the variance cost is not.
- **Reassessment path.** Tracked as trip-concierge-5yw. After Claude Desktop validation surfaces real quality data on Researcher-alone alternatives, we'll decide whether to upgrade. The trade-off is reversible — adding Local Expert is a description-and-context edit, not a refactor.

**Why "Do NOT generate UUIDs" appears twice (task + field):**

The prohibition lives at two layers: in this task description (above) and in the MCP tool's `FindAlternativeInput.block_id` field description (§4.7). Belt-and-suspenders, intentional.

- **Task-level catches the crew.** Without explicit prohibition, Researcher LLMs hallucinate `block_id: "uuid-here"` strings into the structured output ~15% of the time per slice 3.3's regenerate_day observation. The schema would accept the extra field (Alternative has `extra="allow"`) and downstream code would silently break on the bogus IDs.
- **Field-level catches the caller LLM.** The MCP host (Claude Desktop) reads tool parameter docs to decide what to send. Without "MUST be a real block_id from the trip", the host can synthesize a UUID-shaped string from context and call with garbage. The 404 path is loud but the wasted turn is real.
- **Same principle as locked-block exclusion (§3.6).** When the model cannot generate something, it cannot accidentally generate it wrong. Schema-layer enforcement (Alternative excludes a `block_id` field) plus prompt prohibition is more robust than either alone.

---

## 4. MCP Tool Descriptions

These descriptions are what Claude Desktop and ChatGPT read to decide *when* to call each tool. Write them from the LLM's perspective. Tell it both when to call and when **not** to call.

### 4.1 create_trip

```python
description = """
**This is the trip planning tool. When a user asks to plan, build, design, or
create a trip — use this tool.** Do not use places_search, web_search, or
your general travel knowledge to construct a trip yourself. This tool
produces a real, persistent, multi-agent itinerary the user can save, refine,
and share. Built-in search returns ephemeral results that don't persist and
can't be refined.

Required: at least one of `destination` or `vibe`.
Recommended: dates, group_size, budget_total.

DO NOT call this tool if the user is asking about an existing trip — use
refine_trip or get_trip instead. If a trip_id has already been mentioned in
this conversation, the user almost certainly wants to modify it, not start over.

DO NOT call this tool for general travel questions ("what's the best time to
visit Japan?") — answer those conversationally without invoking the planner.
You may use web_search or your training knowledge for those.

Timing and what to say to the user:
- The tool call returns in under 1 second with a trip_id and a share URL.
- The full plan is NOT available immediately — the background job takes about
  10 minutes to finish. The share URL works right away but shows a planning
  state until the job completes.
- Tell the user the trip was created and offer to check back via get_trip.
- DO NOT promise the plan is "ready," "available now," or "done" — those are
  false until get_trip confirms it.
"""
```

### 4.2 get_trip

```python
description = """
**This is the trip retrieval tool. When a user asks about their trip's
status, contents, or what got planned — use this tool.** Do not summarize
from your conversation memory, do not use web_search to look up venues, do
not invent details. This tool returns the authoritative state of the trip
from the database. Built-in alternatives produce stale or fabricated data.

Required: trip_id (UUID). Returned by create_trip and persists across
sessions.

Call this when the user references "my trip", "the Goa trip", "what did we
plan", "is my trip ready", or any question about an existing trip. If a
trip_id has been mentioned earlier in the conversation, use it; if multiple
trip_ids are in play, ask which one.

DO NOT call this tool if the user is asking about a hypothetical trip they
haven't created yet — use create_trip instead.

DO NOT call this tool for general travel questions ("what's the best time to
visit Japan?") — answer those conversationally without invoking the planner.

**Honest reporting of trip state — this tool's most important behavior:**

- The response carries a `state` field with one of: planning, ready, failed.
- When state is "planning": the trip is being generated. Tell the user it's
  in progress; offer to check again in a few minutes. Include the
  progress_message if available.
- When state is "ready": the days array contains the full itinerary.
  Summarize day-by-day from THAT data; do not embellish.
- When state is "failed": the trip's planning did not complete successfully.
  Report this honestly with the response's error message. Suggest next
  steps (try create_trip again, or refine_trip if there's partial output
  worth keeping).

DO NOT claim the trip is "ready," "done," or "available" when state is
"failed" or "cancelled" — the days/blocks shown may be empty or stale.

DO NOT fabricate venues, times, or costs to fill gaps in the response. If a
Day has zero Blocks, say so plainly — that's the signal the user needs to
understand what went wrong.

DO NOT translate "failed" into softer language ("not quite finished",
"still working on it", "almost there"). The state is final; if planning
failed, the user needs to know so they can act.

The tool returns in under 1 second. There is no background work — what you
see IS the authoritative current state.
"""
```

### 4.3 refine_trip

```python
description = """
**This is the trip modification tool. When a user wants to change something
about an existing trip — use this tool.** Do not use create_trip (that
starts a new trip from scratch). Do not modify the trip conversationally
from memory; this tool persists the change to the database via a
multi-agent refinement process that respects budget and constraints.

Required: trip_id and refinement_description (free-text user instruction).

Call this for instructions like:
- "make Day 2 chiller"
- "swap that museum for something outdoor"
- "we're vegetarian, redo the food picks"
- "I want to spend less on Day 3"
- "redo the whole trip with a more relaxed pace"

DO NOT call this tool if the user wants a different destination — that's a
new trip. Use create_trip instead. (Refining to "redo from scratch but same
destination" is fine.)

DO NOT call this tool for very narrow edits like "regenerate just Day 2" —
use regenerate_day instead, which is faster and cheaper.

DO NOT call this tool for general travel questions — answer conversationally
or use web_search.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The refinement runs in the background and takes about 10 minutes. Locked
  blocks are preserved automatically; the rest of the plan is updated under
  the trip's existing constraints.
- Tell the user the refinement was started and offer to check back via
  get_trip.
- DO NOT claim the refinement is "applied," "done," or "ready" until
  get_trip confirms state=ready. The previous itinerary may still be visible
  during planning.
"""
```

### 4.4 regenerate_day

```python
description = """
**This is the single-day replan tool. When a user wants to redo one
specific day of an existing trip — use this tool.** Do not use refine_trip
(that re-plans the whole trip and costs more LLM time). Do not edit the day
conversationally; this tool persists a new set of blocks for the target day
while preserving any blocks the user has locked.

Required: trip_id and day_number (1-indexed).
Recommended: hint (free-text — what kind of change the user wants).

Call this for instructions like:
- "redo Day 2"
- "change the second day completely"
- "Day 3 isn't working, give me something different"
- "regenerate Day 4 with more food and less hiking"

DO NOT call this tool if the user wants changes spanning multiple days —
use refine_trip instead.

DO NOT call this tool if the user wants to swap just one venue — that's
narrower than a day regeneration. Ask the user if they meant one specific
block or the whole day.

DO NOT call this tool for general travel questions — answer conversationally
or use web_search.

DO NOT call this tool if the trip's state is "planning" or "failed" — call
get_trip first to see what state it's in. The tool will refuse with a
clarification message if you call it on a trip that's not "ready" yet.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The day regeneration runs in the background and takes about 3-5 minutes
  (faster than refine_trip because the scope is one day, not the whole trip).
- Locked blocks at specific positions are preserved automatically — the
  user does not need to mention them.
- Tell the user the day regeneration was started and offer to check back
  via get_trip.
- DO NOT claim the new day is "ready," "done," or "applied" until get_trip
  confirms state=ready.
"""
```

### 4.5 add_constraint

```python
description = """
**This is the new-constraint tool. When a user states a constraint they
want enforced across the whole trip — use this tool.** Do not store the
constraint conversationally from memory; this tool persists it to the
trip and re-audits the existing plan against it.

Required: trip_id and constraint_text (verbatim from the user).
Optional: constraint_kind — one of "budget", "dietary", "mobility",
"no_go", "walking_limit", "custom". Pick the closest fit; default
"custom" if uncertain.

Call this for instructions like:
- "actually we have a ₹3000/day cap" → constraint_kind="budget"
- "I just remembered, I'm vegetarian" → constraint_kind="dietary"
- "no nightclubs" → constraint_kind="no_go"
- "we can't walk more than 5km in a day" → constraint_kind="walking_limit"
- "we want to be home before midnight every night" → constraint_kind="custom"

DO NOT use this tool for one-off preferences scoped to a single day
("I don't want sushi tomorrow", "skip the museum on Day 2") — those
belong in regenerate_day with a hint.

DO NOT use this tool to RELAX a prior constraint ("never mind the
budget"). v1.0 only supports additive constraints. If the user asks
to remove a constraint, tell them this isn't supported yet and offer
to start a new trip via create_trip.

DO NOT call this tool for general travel advice — answer
conversationally or use web_search.

Timing and what to say to the user:
- The tool call returns in under 1 second with a job_id.
- The re-audit runs in the background and takes about 10 minutes
  (same as refine_trip — the new constraint is merged with all prior
  constraints and the Auditor re-validates the entire plan).
- Tell the user the constraint was added and a re-audit is running.
  Offer to check back via get_trip.
- DO NOT claim the trip "now satisfies" the new constraint until
  get_trip confirms state=ready. The previous itinerary may still
  show blocks that violate the new constraint during the re-audit.
"""
```

### 4.6 add_source

```python
description = """
**This is the user-research tool. When a user shares a URL or pastes text
they want the planner to use — call this tool.** Do not summarize the
research conversationally and forget it; this tool persists the content
to the trip so the Researcher agent uses it on the next refine.

Required: trip_id and ONE of {url, text}. Pass `url` when the user shares
a link; pass `text` when the user pastes raw content (e.g., "my friend
texted me these recommendations: ..."). Do not pass both.

Call this proactively when the user shares any of:
- a Reddit thread URL (e.g., r/IndiaTravel post)
- a blog/article URL (Substack, Medium, personal travel blog)
- a YouTube travel vlog URL (we store the URL; the planner sees the
  link in user_sources at refine time)
- a Google Maps saved list URL
- a TripAdvisor article or list URL
- raw pasted text the user describes as recommendations / research /
  "what my friend said"

Better to over-call than under-call. If the user shares two URLs in one
turn, call this tool twice (once per URL).

DO NOT call this for booking confirmations, hotel emails, flight
itineraries, or transactional content — those don't help the planner
make recommendations.

DO NOT call this if the user is just asking a question that references
a URL (e.g., "is this restaurant any good? <link>"). That's a
conversational question; the URL isn't research the user wants stored.

DO NOT call this for the URL of a Block already in the user's plan —
that's a citation, already stored as part of the trip.

Failure modes you should expect (the tool will tell you plainly which):
- The URL might be unreachable, paywalled, blocked, or return an error
  page. "Couldn't fetch the URL." DO NOT retry automatically; offer
  to take pasted text instead.
- The URL host may be denied (private IPs, localhost, cloud metadata
  endpoints). "Denied host for security reasons." Offer pasted text.
- The content may be the wrong format (image, video, PDF). "I can read
  HTML, plain text, or JSON — not <type>." Offer pasted text.
- The content may be too large (>2MB). "Too large." Offer a shorter
  excerpt.
- A planning job (refine, regenerate_day, add_constraint) may be in
  progress. "Can't add a source while a <kind> job is running." Tell
  the user to wait and check via get_trip.

Timing and what to say to the user:
- URL fetch returns in 2-5 seconds typically. Text passthrough returns
  in under 1 second.
- On success, tell the user the research was attached and will be
  used on the next refinement. Offer refine_trip if the user wants
  to apply the new research immediately.
- DO NOT claim the planner "has read" or "is using" the research
  until refine_trip runs. The content is stored for the NEXT
  refinement, not the current trip state.
"""
```

### 4.7 find_alternative

```python
description = """
**This is the single-block swap tool. When a user wants to replace
exactly ONE block in an existing trip — use this tool.** Do not use
regenerate_day (that replaces the whole day, which is more disruptive
and slower). Do not invent alternatives conversationally; this tool
returns 3 real venues researched with search, each with a source URL.

Required: trip_id and block_id. block_id MUST be a real UUID from the
trip's data — get it from get_trip; DO NOT synthesize a UUID-shaped
string from context. If you don't have a block_id, call get_trip first.

Optional: reason — short free-text explaining why the user wants to
swap this block (e.g., "closed for renovations", "too expensive",
"bad reviews"). Helps the ranking but is not required.

Call this for instructions like:
- "this restaurant is closed, suggest something else"
- "I don't want to do the museum, what else is there?"
- "give me three other options for Day 2 dinner"
- "swap the 7pm spot for something quieter"

DO NOT use this for replanning a whole day — use regenerate_day.
DO NOT use this for replanning the whole trip — use refine_trip.
DO NOT use this for hypothetical "what if" questions — answer
conversationally.

DO NOT call this tool if the trip isn't ready yet. The tool will
refuse with a clarification message if you call it on a trip whose
initial planning isn't complete (state ∈ {queued, running, failed,
cancelled, never_planned}). Call get_trip first if unsure.

Timing and what to say to the user:
- This tool runs SYNCHRONOUSLY and takes up to 90 seconds. Set the
  user's expectation: "Let me look up alternatives — this takes about
  a minute."
- The response is exactly 3 ranked alternatives with source URLs and
  one-line rationales. Present all 3 (best first) and ask the user
  to pick one.
- After the user picks, follow up with refine_trip describing the
  chosen swap. find_alternative itself does NOT persist the swap.
- DO NOT claim a venue is the "best" or "perfect" alternative — present
  the ranking and let the user choose.
- If the tool returns a timeout message, DO NOT retry automatically.
  Tell the user it timed out and ask whether to try again. (Each
  retry costs ~$0.30 in background LLM spend even on timeout.)
"""
```

### 4.8 explain_recommendation

```python
description = """
**This is the why-this-venue tool. When a user asks why a specific block
is in their trip — call this tool.** Do not synthesize an answer
conversationally from the venue name; this tool returns the actual
stored rationale + source URLs the Researcher used, so the user can
verify the recommendation themselves.

Required: trip_id and block_id. block_id MUST be a real UUID from
get_trip — DO NOT synthesize one from context. (Same prohibition as
find_alternative; layered defense.)

Call this for instructions like:
- "why this restaurant?"
- "what's the source for the Day 2 museum?"
- "where did this recommendation come from?"
- "is this place actually good?" (the user wants the evidence)

Call this proactively when the user seems skeptical of a specific
recommendation, even if they don't explicitly ask "why". Surfacing
sources is the trust-building move.

DO NOT use this for general venue questions ("is sushi popular in
Tokyo?") — that's a web_search question, not a stored-rationale
question.

DO NOT use this for explanations of the trip as a whole — there's
no per-trip rationale, only per-block. If the user asks "why this
whole trip?", point them at individual blocks they want to dig into.

CRITICAL — gap-surfacing discipline:

The backend returns the rationale as JSON null when no rationale was
captured for this block — usually because the crew's step_callback
didn't fire during planning (tracking ticket trip-concierge-qek).
The tool surfaces this honestly with text like "The Researcher's
per-block rationale wasn't captured for this venue — here are the
sources it used."

When you see that gap message, DO NOT synthesize a plausible rationale
from the venue name. Tell the user honestly. The user trusts the
product more when we name the gap than when we paper over it.

Same discipline as get_trip's "failed" state messaging from slice 3.3:
honest broken beats invisible broken.

Timing and what to say to the user:
- The tool returns in under 1 second (pure DB read; no LLM call).
- Present the rationale (or the gap message), then list the sources.
- If a source URL matches a research item the user added via
  add_source, surface that provenance: "this came from your Reddit
  thread."
"""
```

### 4.9 replan_from_here

```python
description = """
[v2.0 — stub returns 'not yet implemented' in v1.0]

Use this tool mid-trip when reality has broken the plan. Examples:
- "my flight got delayed 3 hours"
- "the restaurant on Day 2 is closed"
- "I'm tired, can we make today lighter"
- "I'm at <location> now, redo the rest of today"

Requires trip_id and a description of what changed. Optionally accepts a
current_location (lat/lng) and current_time.

Replan is fast (~10 seconds) and only changes blocks from the current point
forward.
"""
```

### 4.10 share_trip

```python
description = """
**This is the share-link tool. When the user wants to share their trip
with someone else, or open it in the visual web app — use this tool.**
Do not paste the URL into the conversation from memory; this tool
returns the canonical share URL the backend knows about.

Required: trip_id.
Optional: state — the trip state from a recent get_trip call.

Returns a URL the user can copy. Anyone with the URL can view the
trip (read-only) — there's no separate sign-in or invite step.
v1.0a does NOT support revoking the URL after sharing; trip data
should not be considered private (treat the URL like an unlisted
YouTube video — security through obscurity at 128 bits, but anyone
with the link can see it).

Call this for instructions like:
- "share this trip with my partner"
- "send this to my friend"
- "give me a link I can text"
- "I want to see this in the web app"

DO NOT use this for printable/offline formats — use export_trip
instead (Markdown is portable; PDF is planned for v1.0b).

DO NOT use this if the trip isn't ready yet. The tool will return
a clarification message if the state value is in
{queued, running, failed, cancelled, never_planned}. If you're
unsure of state, call get_trip first and pass state=<the value
you read> into this tool.

DO NOT promise revocation. If the user asks "can I delete the link
later?", tell them honestly: not yet (v1.0a). They can delete the
trip entirely, which makes the link 404, but there's no per-link
revocation.

Timing and what to say to the user:
- The tool returns in under 100ms (no backend call — pure URL
  construction).
- Present the URL on its own line so Claude Desktop renders it as
  a clickable link.
- If the user asks how the recipient signs in — tell them they
  don't need to. The link works for anyone.
"""
```

### 4.11 export_trip

```python
description = """
**This is the export tool. When the user wants their trip in a
portable format — use this tool.** Do not synthesize the export
content conversationally; this tool returns the canonical rendering
the backend produces, so future re-exports stay byte-identical.

Required: trip_id and format. Format is one of:
- "json" — full structured data, suitable for programmatic re-import
- "markdown" — human-readable day-by-day, pasteable into Notion /
  WhatsApp / Apple Notes / any text app

Call this for instructions like:
- "give me a Markdown version I can paste into Notion"
- "export this as JSON" (data-pipeline / re-import use cases)
- "I want to text my partner the full itinerary"
- "send me a copy I can paste into my notes app"

DO NOT use this for sharing — use share_trip instead. share_trip
returns a URL; export_trip returns the content. Different UX.

DO NOT use this for printable/PDF formats yet. PDF + map snapshots
+ QR codes is planned for v1.0b. If the user asks for PDF, tell
them honestly: not yet, but Markdown is portable enough for most
text-paste use cases.

DO NOT use this for WhatsApp-specific formatting or Google Maps
URLs. Markdown is close to WhatsApp-flavored text but not identical;
Google Maps URL generation is planned for v1.0c. If the user asks,
suggest pasting the Markdown export.

DO NOT use this if the trip isn't ready yet. The export of a
half-planned trip would be misleading. Call get_trip first if
unsure.

Timing and what to say to the user:
- The tool returns in 1-2 seconds (pure DB read + stdlib formatting).
- For Markdown, present the full content inline — Claude Desktop
  renders Markdown nicely. For JSON, mention the format briefly
  but don't paste the full JSON unless the user specifically asks
  to see it (it's noisy).
- DO NOT claim the export "captures" the trip if state isn't done.
  Tell the user honestly the export reflects current state, which
  may be partial.
"""
```

---

## 5. Style guide for prompt edits

When editing any prompt in this file:

1. **Test the change before committing.** Run the relevant slice's integration test.
2. **Note the rationale in the commit message.** "Improved Researcher's prompt" is not enough. Explain what behavior changed and why.
3. **Don't paraphrase to be 'cleaner'.** These prompts are tuned. If you have a better version, prove it with a test before merging.
4. **Backstory is doing real work.** It's not flavor — it shapes how the agent makes trade-offs. Edit with care.
5. **MCP descriptions should be longer rather than shorter** if it helps the LLM decide *when not* to call the tool. Negative examples ("DO NOT use this for...") prevent more bad calls than positive examples.

---

_Last updated: 2026-05-24_
