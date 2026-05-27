# Rule: Refactor follow-ups — audit path-relative logic

**Status:** Hard rule for any commit that moves files between directories.

## Why

File moves break code that knows its own location. The tests pass because the moved code's *imports* still resolve (Python found the new path) — but anything reasoning about `__file__` or working directory now points somewhere different, and unless the new path happens to also exist, the failure is silent.

Worst case: the new path exists with stale data, and the code "works" but reads from the wrong source.

We hit this in slice 2.5b. `agents/src/trip_agents/config.py` had `_REPO_ROOT = Path(__file__).resolve().parent.parent` — correct under the flat layout (`agents/config.py` → two parents up = repo root). After slice 2.5a's src-layout move (`agents/src/trip_agents/config.py`), two parents up resolves to `agents/src/` — wrong. The pydantic-settings env-file fallback pointed at a path that didn't exist, but **shell env always supplied the secrets during dev runs**, so nothing visibly broke. Discovered by accident a slice later while wiring `redis_url` into the same Settings class.

This is a silent-breakage class. Tests pass. Lint passes. CI passes. Behavior shifts. The bug is the offset between "where the code thinks it is" and "where it actually is."

## The rule

After any commit that moves files between directories, **run a deliberate path-audit pass** before the commit ships. Grep for the following patterns in the moved files (and in any file that imports the moved code):

```
Path(__file__)
__file__
os.path.dirname(__file__)
os.path.abspath
os.getcwd()
.glob(
.rglob(
pathlib.PurePath
```

For each hit, verify by reading the surrounding code:

1. **What location is this expression resolving?** Walk the `.parent` / `.parent.parent` count and confirm the result against the new file location.
2. **Is the result hard-coded against a directory layout that just changed?** If yes, the expression is suspect.
3. **Is the result used to find a file?** If yes, verify that file exists at the resolved path. `Path(...).exists()` is your friend.

Common offenders:

- `Path(__file__).parent / ".." / "config.yml"` — counts parents wrong.
- Config-file discovery: `dotenv.load_dotenv(parent_dir / ".env")` — silently no-ops if the path is wrong.
- Test fixtures: `FIXTURE_PATH = Path(__file__).parent / "fixtures" / "x.json"` — fails loudly if the fixture is missing (this is good).
- Working-directory assumptions: `open("README.md")` from a tool that used to live at repo root but moved down a level.

## Add path-audit to the slice acceptance checklist

For slices that include file moves, the "Done when" criteria should explicitly include:

- [ ] Ran `grep -rn 'Path(__file__)\|os.path.dirname(__file__)\|os.getcwd()\|\.glob(' <moved-paths>` and walked every hit.
- [ ] For each path-resolution hit, confirmed the resolved path exists with `Path(...).exists()` (or equivalent).

This catches the bug before commit, not slices later.

## Test discipline that helps

Two complementary patterns make path bugs noisier:

1. **Path-resolution at module top, not lazy.** `_REPO_ROOT = Path(__file__)...` at import time means import-time `FileNotFoundError` or `ValueError` if the path is structurally invalid (e.g., walks above the filesystem root). Better than lazy resolution that fails only when the path is accessed.

2. **Existence assertion at import.** If a module depends on a discovered file (config, fixture), `assert _PATH.exists(), f"missing {_PATH}"` at module top fails loudly at import. Tests catch it instead of shell-env-masking.

Apply discipline #2 sparingly — only where the file is genuinely required at import.

## Reference

- Slice 2.5a → 2.5b discovered `agents/src/trip_agents/config.py:_REPO_ROOT` was off by one `.parent` after the src-layout move. Shell env masked the breakage for an entire slice. Fixed in commit `b05096a` while adding `redis_url`.
- See also `.claude/rules/commit-decomposition.md` rule 1 — refactor-only commits should have the path audit done as part of them, before the new-code commits land on top.

---

_Last updated: 2026-05-27._
