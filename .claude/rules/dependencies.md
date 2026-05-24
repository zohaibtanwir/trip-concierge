# Rule: Dependency hygiene

**Status:** Hard rule. CI enforces several of these mechanically.

## The threat landscape

Between March and May 2026, the npm and PyPI ecosystems have been hit by sustained, coordinated supply chain attacks. Confirmed compromises include Axios, TanStack (42 packages), Mistral AI SDK, Guardrails AI, node-ipc, Bitwarden CLI impersonation, and Laravel-Lang (700+ versions). The attackers target cloud credentials, CI/CD secrets, GitHub tokens, and SSH keys.

Treat every transitive dependency as potentially hostile.

## Rules

### 1. Pin everything exactly

- `package.json`: every entry uses an exact version. No `^`, no `~`, no `>=`.
- `pyproject.toml`: same. Use `==`.
- Lockfiles (`pnpm-lock.yaml`, `uv.lock`) are committed.

### 2. No ad-hoc installs

- Always go through the lockfile: `pnpm add <pkg>` or `uv add <pkg>`.
- Never `npm install` directly.
- Never `pip install` directly.
- CI uses `pnpm install --frozen-lockfile` and `uv sync`.

### 3. Ignore install scripts by default

- `.npmrc` sets `ignore-scripts=true`.
- Packages that genuinely need install scripts get explicit allowlist entries with a reason in the commit message.
- This single setting would have blocked the Axios, node-ipc, and Bitwarden CLI attacks.

### 4. Denylist (CI enforces)

These packages are blocked. CI fails if they appear in any lockfile.

**npm:**
- `axios` (compromised March 2026; use native fetch or ky)
- `node-ipc` (compromised May 2026)
- `@tanstack/*` (compromised May 2026)
- `mistralai` (compromised May 2026)
- `@uipath/*`, `@squawk/*` (compromised May 2026)
- `intercom-client`, `opensearch-project/opensearch` (compromised May 2026)

**PyPI:**
- `mistralai` (compromised May 2026)
- `guardrails-ai` (compromised May 2026)

Reintroduction: never within 60 days of compromise disclosure. After 60 days, requires explicit PR with rationale and audit notes.

### 5. New dependency checklist

Before adding any dependency:

- [ ] Search on socket.dev or snyk.io. Read the most recent advisories.
- [ ] Check publish history. Sudden bursts of activity from a new maintainer = walk away.
- [ ] Check maintainer count. Bus factor of 1 with sensitive scope = walk away.
- [ ] Check the install scripts. Any `postinstall`, `preinstall`, `install` script = needs explicit allowlist.
- [ ] Pin the version exactly when adding.
- [ ] Update the tech stack table in `CLAUDE.md` if it's a top-level dep.
- [ ] Update `BUILD_PLAN.md` with the rationale (in the relevant slice).

### 6. Lockfile changes get a second pair of eyes

Any PR that changes a lockfile is reviewed by a second person before merge, including Dependabot/Renovate PRs. Don't auto-merge dependency updates.

### 7. GitHub Actions hardening

- No `pull_request_target` workflows. This is the vector that compromised TanStack.
- All Actions pinned to full SHA, not tag. `uses: actions/checkout@v4` is wrong; use the SHA.
- `permissions:` declared at workflow level, default to `contents: read`.
- No secret access from workflows that handle forked PRs.
- OIDC trusted publishing for any package we publish (we don't currently publish, but the rule stands).

### 8. Egress monitoring

In production and CI, log all egress. Alert on connections to non-allowlisted destinations. Block IOCs from current threat advisories. The MCP server and FastAPI service have allowlists for outbound connections (LLM provider, search APIs, telemetry).

### 9. Secret rotation

- Static tokens rotated quarterly, even without incident.
- Prefer OIDC over static tokens wherever the platform supports it.
- Anthropic, Tavily, Serper, and Google OAuth keys are tracked in a rotation calendar.

## What to do if a dep we use gets compromised

1. **Stop the bleeding.** Pin to a known-clean version immediately. If no clean version exists, remove the dep.
2. **Rotate any secrets** that could have been exfiltrated by a CI runner or dev machine that installed the bad version.
3. **Audit logs** for the time window between compromise publication and our pin. Look for unusual egress.
4. **Add the package to the denylist** in this file.
5. **Open an incident retrospective** in the repo issues.

## What this rule does NOT cover

- Application-level security (auth, authz, input validation) — see `docs/prd.md` §5.3.
- Runtime sandboxing of agent tools — separate concern, in `BUILD_PLAN.md` Phase 5.

---

_Last updated: 2026-05-24. Review monthly during v1.0 build._
