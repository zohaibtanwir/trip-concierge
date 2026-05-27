# Rule: Git discipline

**Status:** Hard rule. Captures real footguns surfaced during build.

## 1. Always `git add <renamed-path>` after editing a renamed file

If you `git mv old.py new.py` (or any sequence that ends with a rename in the index) and then modify the file via `Write` or `Edit`, the index still holds the *original* content with rename detection — your edits are **not staged**.

The commit will ship the file with stale content. CI doesn't catch it for renamed test files because live tests skip in CI.

**Rule:** after any sequence of (rename → edit), explicitly run:

```
git add <new-path>
```

before committing. Don't rely on `git status` looking right — the rename will say "RM (renamed)" while your edits sit unstaged in the working tree.

**Origin:** slice 2.3, commit `46123eb` shipped `agents/tests/test_pipeline_live.py` with the slice-2.2 assertions because of this pattern. Fix landed in `70600d1` as a follow-up commit on main.

## 2. Never `git commit -a` to "just stage everything"

Always stage specific files. `-a` skips untracked files (which surprises you on first commits of a new feature) and can sweep in unrelated dirty state. The seconds saved aren't worth the loss of intent.

## 3. Never `--no-verify`

Pre-commit hooks exist because lint or types caught something. Bypassing them ships broken code to PR review (where it'll fail CI anyway) or to `main`. If a hook is genuinely wrong for a commit, fix the hook or the code — don't skip.

The only exception is bd's own `pre-commit` hook complaining about JSONL flushing on a machine where bd isn't installed — that's a non-issue and the hook handles it internally. We don't have that case in the project.

---

_Last updated: 2026-05-27._
