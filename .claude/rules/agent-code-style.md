# Rule: Agent code style

**Status:** Hard rule for anything under `agents/`.

## Why

The CrewAI agents are the product's brain. Inconsistent agent code makes debugging impossible — when behavior drifts, you can't tell whether the cause is the prompt, the tool, the LLM, or the composition.

## Source of truth

`agents/prompts.md` is the canonical source for every agent's `role`, `goal`, `backstory`, and every MCP tool's `description`. Python files import from or copy verbatim from that file.

## Rules

### 1. Never modify role/goal/backstory in source without updating `agents/prompts.md` first

Every PR that touches these strings must update `agents/prompts.md` in the same commit. CI checks for divergence.

### 2. Agents go in one file each

```
agents/
├── researcher.py
├── local_expert.py
├── logistics.py
├── budget_auditor.py
├── crew.py          # composition only, no agent defs
├── tasks.py         # task definitions, one function per task
├── tools/
│   ├── web_search.py
│   ├── maps_api.py
│   └── ...
└── prompts.md       # canonical source
```

### 3. Tools are pure functions where possible

A tool function:
- Takes typed inputs
- Returns typed outputs (Pydantic model preferred)
- Logs structured events on call, success, failure
- Times out — never blocks forever
- Has unit tests with the LLM mocked out

### 4. Every agent call is traced

CrewAI integrates with Langfuse. Every `crew.kickoff()` produces a trace with per-agent breakdown. Tests assert traces exist (not their content).

### 5. Delegation is intentional

`allow_delegation=True` is the default for all four agents, but the delegation chain should be obvious from the prompts and task `context=[...]`. If a new agent is added, its delegation policy is documented in `agents/prompts.md`.

### 6. Process selection is explicit

`build_crew(process=Process.sequential)` and `build_crew(process=Process.hierarchical)` are the two entry points. The choice is made by the caller, not buried inside the crew module. Sequential for initial generation; hierarchical for refinement.

### 7. Memory is per-user

CrewAI's memory is enabled but scoped per user. The `user_id` is passed into every crew kickoff. Tests verify isolation — one user's memory never leaks into another's run.

### 8. No prompt injection from user input

User-supplied strings (destination, vibe, constraint text, BYO research) are passed to agents as **data**, not concatenated into prompts. Use CrewAI's task input variables, not f-string interpolation into the role/goal/backstory.

Wrong:
```python
researcher = Agent(
    role=f"Travel researcher who knows {user_destination} well",  # injection vector
    ...
)
```

Right:
```python
research_task = Task(
    description="Find venues in {destination}",  # CrewAI template var
    agent=researcher,
)
crew.kickoff(inputs={"destination": user_destination})
```

### 9. LLM choice is centralized

The LLM (model name, API key, parameters) is configured in `agents/llm.py` and imported by all agents. Do not hardcode `model="claude-sonnet-4"` in individual agent files.

### 10. Costs are observable

Every agent run logs token usage and cost to Langfuse. The `/admin/costs` page surfaces this. No agent invocation happens without cost tracking.

## What goes wrong if these rules slip

- Prompts drift between source and `prompts.md` — debugging becomes archaeology
- Agents get hardcoded LLM choices — multi-provider becomes a rewrite
- User input flows into role strings — prompt injection becomes an attack vector
- Delegation chains spread across files — behavior changes have unpredictable scope

Slow down. Read `agents/prompts.md`. Then edit.
