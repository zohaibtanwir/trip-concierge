# Rule: Slice completion discipline — `bd close` AFTER merge, never before

**Status:** Hard rule. Beads state must reflect what is on `main`, not what is "ready to merge."

## Why

The natural pull is to mark a ticket closed as soon as the work *feels* done — PR opened, CI green, code reviewed. That feeling is wrong. Until the merge button is pressed and `main` actually contains the change, the work is not done — the PR could be force-pushed over, closed without merge, conflict with a parallel merge, or sit waiting on a final reviewer.

When `bd close` happens before the merge, Beads becomes a lie. `bd ready` then surfaces downstream slices as unblocked when their dependency isn't actually on main yet. The next session picks up the next slice and starts referencing files / endpoints that don't exist in the branch they just `git pull`'ed.

The cost of getting this wrong is silent — no test fails, no warning prints. You discover it when 3.2 imports a symbol from 2.5c's not-yet-merged code and the build breaks on a clean clone.

## The rule — post-PR-approval checklist, in order

After a PR is approved:

1. **Push** the branch (you've already done this to open the PR).
2. **Open the PR** (already done).
3. **Wait for CI green** — every required check, not "most of them."
4. **Merge the PR** — squash + delete branch. This is the step that gets skipped or postponed.
5. `git checkout main && git pull` — verify the merge commit is local.
5a. **If the slice added a migration:** run `make db.migrate` locally against the dev DB and verify `alembic_version` matches the new head. The CI test DB getting `upgrade head` automatically per test session does NOT mean the dev DB advanced — they're different databases. See "How step 5a entered the rule" below.
5b. **If the slice modifies a long-lived worker process** (arq workers, daemons, agent loops, MCP server stdio process), restart the worker after merge AND before declaring the slice complete. Verify the new code is loaded by checking a process attribute (PID changed, start time matches the restart, etc.). For dzc-a / qek-a style observability slices: ALSO trigger a known input that exercises the new instrumentation, to confirm the wiring fires end-to-end. A merged-but-not-running observability commit is silently broken. See "How step 5b entered the rule" below.
6. `bd close <ticket-id>` — only now.
7. `bd ready` — confirm the next slice surfaces clean and the dependency graph is honest.

`bd close` at step 6, never earlier. Even if the merge is "going to happen in a minute" — wait the minute.

## What violation looks like

Slice 2.5c (2026-05-27) shipped as PR #17. The Beads ticket `trip-concierge-zyy` was closed before the PR was merged. The mismatch lived for some hours: `bd list` showed Phase 2 complete while a Phase 2 slice's code was still on a feature branch.

Caught when running `bd ready` before starting 3.2 — noticed slice 2.5c was missing from the open list despite the PR being visibly open in GitHub. **Caught by luck during a progress audit, not by any check that would have caught it automatically.** The rule exists so that the catch isn't required.

## What this rule does NOT cover

- **Bug-fix PRs** that aren't tracked in Beads (one-line fixes, doc tweaks). No ticket to close.
- **Multi-PR slices** where part of the work is intentionally split across PRs. `bd close` waits until the LAST PR for that ticket is merged.
- **Reverts** — if a merge is reverted, re-open the ticket with `bd reopen` and note the revert reason.

## Recovery if you violated the rule

You spot a ticket marked closed while its PR is still open:

1. **Do not start downstream work** based on that ticket's existence in `main`.
2. Either merge the PR (preferred — finish what was started) or `bd reopen <id>` (if the PR is going to be abandoned).
3. Audit any tickets unblocked by the prematurely-closed one — they may have already been claimed and their authors may be referencing code that isn't on main yet.

## How step 5a entered the rule

Slice 3.2 validation (2026-05-28) surfaced a class of bug invisible to CI: the dev DB had drifted three migrations behind code (alembic_version=0002 while code expected 0005). Slices 2.4, 2.5b, and 2.5c had each added a migration; each was applied to the CI test DB via `conftest.py:db_engine` running `command.upgrade(cfg, "head")` per session; the dev DB was never re-migrated. Five MCP scenarios passed validation at the tool layer; meanwhile the worker silently crashed mid-job on every plan request and burned ~$0.80 of real LLM spend producing crew output that couldn't be persisted.

Backend startup now refuses to come up on alembic mismatch (see `backend/app/db/startup_check.py`, added in the slice 3.2 postmortem). That catches the drift on next restart. But the catch is at restart-time, not commit-time. Step 5a moves the audit earlier — to the moment a migration first lands on main — so the fix happens before the next slice begins and before the next manual test burns money.

## How step 5b entered the rule

Slice dzc-a + qek-a (2026-05-30) shipped three observability commits across two PRs: dzc-a (PR #25, merge SHA a9c5b73) instrumented `_extract_trip_plan` to dump raw crew output on failure; qek-a (PR #26, merge SHA aa5abfd) added structured callback firings + a `callback_summary` JobRun entry. Both merged to main cleanly with CI green.

Approximately 12 hours later, the dzc bug reproduced on a fresh Pondicherry trip (`c4b423f5-3731-437a-8aec-8c9d27ef21d7`). The ~7-minute failure had the identical `input_value={}` fingerprint as the original Goa failure that motivated dzc-a. The dev investigation went to `ls /tmp/crew_failure_*.json` to read the dump — and found no files. `JobRun.error` for the failed run had the pre-dzc-a format (no `failure dump:` note appended). `JobRun.agent_summary` was the empty array `[]` with no qek-a `callback_summary` entry.

Root cause: `ps aux | grep arq` showed the worker process (PID 58377) was launched on Thu May 28 11:00 — **two days before the May 30 observability merges.** The worker had been running stale code through the dzc reproduction. The merged-but-not-running observability fired exactly zero times against the failure it was designed to diagnose.

The class of bug is shaped like step 5a's migration drift but with a different runtime asset:
- **Step 5a (migration drift):** dev DB is behind code; CI uses a different DB so doesn't catch.
- **Step 5b (worker drift):** running worker is behind code; tests run the new code in-process so don't catch.

Same shape, different "runtime that's out of sync with main." Both fail silently for the same reason — the gap between "merged" and "loaded by the running process."

The agentic-systems subtlety: with multi-minute feedback loops (a single crew run is ~9 min and ~$0.40), you cannot afford to wait passively for the next failure to validate that observability fires. After a worker restart, deliberately trigger a known input that exercises the new instrumentation. For dzc-a, that's a fresh `create_trip` with the same shape as the bug-triggering input. For qek-a, it's any `create_trip` (the callback_summary entry should appear in `agent_summary` for every JobRun, success or failure).

## Mechanical guard (future)

A post-merge git hook or GitHub Action could close the bd ticket automatically when a PR with `Refs: <ticket-id>` lands on main. Not yet built — would belong as a small slice in Phase 5 alongside other ops automation. Until then, this rule is the manual guard.

---

_Last updated: 2026-05-27._
