# Rule: Architectural checkpoints — file-tree before code

**Status:** Hard rule for slices that touch cross-project boundaries. No exceptions.

## Why

Architectural mistakes are cheap before code exists and expensive after. A nested-directory collision, a wrong namespace name, a cycle in the workspace dep graph — all are 30-second conversations as a file-tree proposal, multi-hour cleanups as committed code.

The tree-before-code gate has caught real bugs at zero cost twice already in this project:

- **Slice 2.5a:** Initial proposal had `agents/agents/` nested-directory layout. User pushed back to src-layout (`agents/src/trip_agents/`). Saved a rename PR.
- **Slice 2.5b:** Initial proposal had worker living in `agents/`. Writing code surfaced the workspace-cycle problem (backend already depends on `trip_agents`; worker would need backend's models, inverting the graph). Caught during the writing phase but would have been caught at the tree-proposal stage if I'd diagrammed the import direction.

In both cases, fixing at the file-tree stage cost a few sentences. Fixing post-code would have been a multi-commit untangle.

## The rule

For any slice that touches **cross-project boundaries**, propose the file tree before writing code. Cross-project boundaries include:

- A new workspace member.
- A new top-level package directory.
- A new service (separate process, deployed independently).
- A refactor that moves files across project boundaries.
- An import direction change (project A starts importing from project B for the first time).
- A new shared schema or model crossing between projects.

**Required cycle:**

1. **Propose** — file tree with every file MOD / NEW / DELETED labeled. Annotate cross-project imports explicitly.
2. **User refines** — pushes back on layout choices, naming, scope.
3. **Re-propose** if needed, until user approves.
4. **Then write code.**

**Skip rate: zero.**

The temptation to skip rises with momentum and shipping pressure. Resist it. The file-tree conversation is rarely the slow part; usually it's the substrate that makes the code-writing fast.

## What this rule does NOT cover

- **Single-project changes** that don't touch boundaries: a new route inside backend, a new agent inside agents, a new test file. Just write the code.
- **Bug fixes** scoped to one file. Just fix.
- **Doc-only changes.** No tree needed.

## What to put in a file-tree proposal

```
project-a/
├── existing.py            MOD   what changes and why
├── new_module.py          NEW   one-line purpose
└── tests/
    └── test_new.py        NEW   how it's tested
```

Plus, for cross-project work:

- **Import direction diagram** if non-trivial. Even ASCII:
  ```
  backend → trip_agents.schemas  (workspace dep, established slice 2.5a)
  backend → trip_agents.crew     (NEW this slice — confirm no cycle)
  ```

- **Risk callout** for anything you're unsure about. The user can correct earlier than you can discover.

## Reference

- Slice 2.5a — initial nested-directory proposal corrected to src-layout via tree review.
- Slice 2.5b — initial worker-in-agents proposal corrected to worker-in-backend during writing (caught by import error, but would have been caught at tree review if dep direction had been drawn).

---

_Last updated: 2026-05-27._
