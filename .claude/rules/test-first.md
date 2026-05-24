# Rule: Test first

**Status:** Hard rule for new features and bug fixes. Soft rule for exploratory spikes (which must be deleted or converted before merge).

## Why

A failing test before implementation forces clarity on what "done" means. Without it, scope creeps, edge cases get missed, and reviewers can't tell whether the code does what it claims.

## What this looks like

For every new feature or bug fix, the first commit in the PR should be a failing test. The second commit (or more) is the implementation that makes the test pass.

```
git log --oneline feature/some-thing
abc1234 feat: implement <thing>
def5678 test: failing test for <thing>
```

## Where tests live

```
backend/tests/<mirror of app/>
mcp_server/tests/<mirror of server source>
web/tests/<mirror of components/, lib/>
```

## Naming conventions

- Python: `test_<module>_<scenario>.py` with functions `test_<scenario>_<expected_behavior>`
- TypeScript: `<component>.test.ts` with `describe`/`it` blocks

## Test types and when to use each

| Type | Tool | When |
|---|---|---|
| Unit | pytest, vitest | Pure logic, single function, no I/O |
| Integration | pytest-asyncio, vitest | Multiple modules together, in-memory DB |
| End-to-end | Playwright | Full user flow through the browser |
| Live | pytest (marked `@pytest.mark.live`) | Real LLM / API calls; skipped in CI |
| Snapshot | vitest | Stable rendered output |

## What NOT to test

- Don't test framework code (FastAPI's routing, Next.js's rendering)
- Don't test that mocks were called in trivial cases — test the behavior
- Don't test private implementation details that change as the design evolves

## When you're tempted to skip

You're never too senior to write the test first. The 30 seconds saved isn't worth the review back-and-forth or the bug that gets in.

If the test is hard to write, the design is probably wrong. That's the signal — pause and rethink before powering through.
