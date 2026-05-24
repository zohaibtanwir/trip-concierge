# Rule: No axios, ever

**Status:** Hard rule. CI enforces this.

## Why

Axios versions 1.14.1 and 0.30.4 were published as malicious npm packages on March 31, 2026 by North Korean state actor Sapphire Sleet. They deployed a cross-platform RAT via a phantom dependency (`plain-crypto-js@4.2.1`). At the time of the compromise, axios had 70-100M weekly downloads.

While the compromised versions have been removed, the broader risk profile remains: axios has a single dominant maintainer account, install scripts in its dependency tree, and a track record of being targeted. Avoiding it eliminates an entire class of supply chain risk.

## What to do instead

For most HTTP needs in this codebase, use **native `fetch`**. It is supported in:
- Node.js 18+
- All modern browsers
- Next.js (both server and client components)
- Python's `httpx` for backend code

If you need a more ergonomic wrapper than native fetch:
- TypeScript: **`ky`** (small, modern, well-maintained, no axios in its tree)
- Python: **`httpx`** (we already use this)

## What CI checks

- `grep -r "from 'axios'" web/ mcp_server/` returns no matches
- `grep -r '"axios"' web/package.json mcp_server/pyproject.toml` returns no matches
- `pnpm why axios` returns "not found"
- If axios appears as a transitive dependency, the build fails and we open an issue to find a replacement for the parent package

## When to revisit

After 90 days from the most recent compromise event involving axios, we may revisit. Until then: no.

## Exceptions

None. If a third-party SDK we genuinely need depends on axios transitively, we either:
1. Find an alternative SDK
2. Vendor the parts we need
3. Wait for the SDK maintainer to migrate

No silent exceptions. Every case is a PR with rationale.
