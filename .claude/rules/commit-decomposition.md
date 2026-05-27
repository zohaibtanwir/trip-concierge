# Rule: Commit decomposition

**Status:** Hard rule for slices that mix refactor and new code. Soft guidance for the rest.

## Why

Single-commit slices that bundle a mechanical refactor with new behavior make every later question harder:

- *"Did the test failure come from the rename or the new code?"* — answer requires bisecting inside the commit.
- *"Can I revert just the new behavior and keep the refactor?"* — answer is no, you revert both.
- *"Is the lockfile change from the refactor or the new dep?"* — diff readers can't tell.

Decomposed commits land the same code with a shape that survives later reviews, reverts, and forensics.

## The rule

For any slice that **mixes refactor and new code**, split into separate commits, **in this order**:

1. **Mechanical-move / refactor first.** Renames, file moves, import rewrites, structural changes that preserve behavior. Must pass CI by itself. No new features.
2. **Housekeeping second.** Doc updates, rule files, retro notes that follow from the refactor. Small. Optional — fold into commit 3 if the housekeeping is trivial.
3. **New code third.** The actual feature work that motivated the slice. Sits on top of the verified-clean refactor.

**Each commit must independently:**
- Pass `make check` (ruff + mypy + biome + tsc clean).
- Pass `make test` (no flakes introduced by the commit).
- Be revertable in isolation — i.e., reverting commit 3 returns to a working refactored state; reverting commit 1 returns to the pre-refactor state.

**Single-commit slices are fine when:**
- The work is pure-new (no preexisting code touched).
- The work is pure-refactor (no behavior change).
- The slice is small enough that the diff is obviously one logical change.

## When to skip decomposition

If you're tempted to skip, ask yourself: *"if this commit ships a regression, will I be able to bisect to the line that broke things?"* If the answer is "I'd have to look inside the commit," decompose.

## Reference

Slice 2.5b shipped as three commits inside one PR:

- `b05096a` queue infrastructure (arq, worker, JobRun model, 4 new files, 5 new tests)
- `6268aba` housekeeping (one-line CLAUDE.md addition)
- `56feeff` (squash) new code wiring `POST /trips/{id}/plan`

CI was run independently against the first two before commit 3 landed. The middle commit caught a CLAUDE.md drift that would have hidden inside the larger PR if we'd bundled.

Slice 2.5a similarly shipped as a refactor-then-wiring pair: `d78a24e` moved agents code to `src/trip_agents/`, then `0a8ffb3` added the FastAPI service. The refactor commit's job was to make CI green with zero behavioral diff.

---

_Last updated: 2026-05-27._
