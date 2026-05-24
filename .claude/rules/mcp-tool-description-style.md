# Rule: MCP tool description style

**Status:** Hard rule for any MCP tool definition in `mcp_server/tools/`.

## Why

The `description` string is the only thing Claude Desktop and ChatGPT read to decide *when* to call your tool. A bad description either causes:
- **Under-calling**: the right tool sits unused while the model improvises
- **Over-calling**: the tool fires for queries it shouldn't handle, costing tokens and confusing users

Both are worse than no tool at all. Treat the description as production prompt code.

## Required structure

Every MCP tool description has three parts:

```
1. WHAT it does (one sentence)
2. WHEN to call it (concrete examples of user intent)
3. WHEN NOT to call it (negative examples + alternative tool to use instead)
```

Optional but recommended:
- Latency expectation (so the model can set user expectations)
- Required vs optional parameters
- Side effects (writes, deletes, irreversible actions)

## Example (good)

```python
description = """
Use this tool to retrieve the current state of a trip the user has already created.
You will need a trip_id, which is returned by create_trip and persists across
sessions.

Call this when the user references "my trip", "the Goa trip", "what did we plan",
or similar — and you have a trip_id available in the conversation context or
recent history.

DO NOT call this if the user is asking about a hypothetical trip they haven't
created yet. Use create_trip instead.

Returns the full trip object including days, blocks, sources, and agent activity.
The response is suitable for natural-language summarization back to the user.
"""
```

## Example (bad)

```python
description = "Gets a trip by ID."
```

This is the API doc. It tells the LLM nothing about when to call it.

## Anti-patterns

- **Too vague**: "Helps with travel planning" — useless for routing
- **Too positive-only**: only saying when to call, never when not to — leads to over-calling
- **Implementation details**: "Calls the /trips/{id} endpoint" — the LLM doesn't care
- **Duplication with parameter descriptions**: the parameter docstrings handle "what `trip_id` is"; the tool description handles "when to use this tool"

## Source of truth

All MCP tool descriptions are maintained in `agents/prompts.md`. Source files import them or copy-paste them with a comment pointing back. Do not edit descriptions in Python source without updating `agents/prompts.md` in the same PR.

## How to test a description change

1. Edit the description in `agents/prompts.md`
2. Update the source file
3. Restart the MCP server in Claude Desktop
4. Open a fresh conversation
5. Try 3-5 user phrasings that should trigger this tool
6. Try 3-5 user phrasings that should NOT trigger this tool
7. Observe which ones routed correctly
8. Iterate on the description until it routes well

This is qualitative, not automated. Document the test phrasings in the PR description.
