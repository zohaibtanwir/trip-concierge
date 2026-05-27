# BUILD_PLAN.md

Vertical slices in build order. Each slice is sized for 1-3 Claude Code sessions. A slice is **done** when:
- The "Done when" criteria pass
- The associated test(s) pass
- `make check` passes (lint + typecheck)
- The slice is marked `[x]` here with a commit SHA

If a slice runs over 3 sessions, decompose it into sub-slices in a new PR before continuing.

---

## Phase 0 — Foundations (Week 1, days 1-2)

### Slice 0.1: Repo skeleton

- [x] **Done when:** `make setup` works on a fresh clone. Empty FastAPI returns `{"ok": true}` on `/health`. Empty Next.js page loads at `localhost:3000`. Empty MCP server starts and lists zero tools. *(Landed across 8adce55, 707ad16, 531ecb2, 2da4457; Beads `trip-concierge-q63` closed.)*
- **Files to create:**
  - `Makefile` with `setup`, `dev`, `test`, `check` targets
  - `backend/pyproject.toml` with FastAPI, uvicorn, pydantic, mypy, ruff, pytest pinned exact
  - `backend/app/main.py` with `/health` route
  - `web/package.json` with Next.js 15, Tailwind, biome pinned exact
  - `web/app/page.tsx` with placeholder
  - `mcp_server/pyproject.toml`
  - `mcp_server/server.py` with empty tool registration
  - `.env.example` with all variables from CLAUDE.md
  - `.gitignore`
- **Tests:**
  - `backend/tests/test_health.py` — assert `/health` returns 200
  - `web/tests/smoke.test.ts` — assert page renders
- **Notes:** Use `pnpm` not `npm`. Use `uv` not `pip`. All deps pinned exact.

### Slice 0.2: CI pipeline

- [x] **Done when:** PR triggers a CI run that executes `make check && make test` and fails if either fails. GitHub Actions pinned to full SHAs. `pull_request_target` is not used anywhere. *(Landed as PR #1, squashed to a94afd1; Beads `trip-concierge-dr6` closed. Failure path verified live: green → fail on F401 → green after revert.)*
- **Files to create:**
  - `.github/workflows/ci.yml`
  - `.github/dependabot.yml` (groups dependencies, opens PRs not merges)
- **Tests:** open a PR that intentionally breaks lint; confirm CI fails.

### Slice 0.3: Pre-commit hooks and Beads init

- [x] **Done when:** `git commit` runs ruff, biome, and rejects if either fails. `bd ready` returns the first seeded ticket. *(Landed as PR #4, squashed to 9cc29c2; Beads `trip-concierge-6xp` closed. Failure path verified locally: stage unused `import os` → ruff F401 → commit rejected.)*
- **Files to create:**
  - `.pre-commit-config.yaml`
  - Seed Beads tickets from this file (one per Phase 0/1 slice initially)

---

## Phase 1 — Data model + first agent (Week 1, days 3-5)

### Slice 1.1: Postgres + Alembic

- [x] **Done when:** `make db.migrate` creates the `users` and `trips` tables on a fresh DB. `psql` shows them. Connection happens via `DATABASE_URL`. *(Landed as PR #5, squashed to 1e7cf6e; Beads `trip-concierge-kbd` closed. pgvector/pg16 image, single Postgres across dev/CI/prod.)*
- **Files to create:**
  - `backend/app/db/base.py` (SQLAlchemy)
  - `backend/app/db/migrations/env.py`
  - `backend/app/db/migrations/versions/0001_initial.py`
  - `backend/app/models/user.py` (id, email, name, preferences JSONB, created_at)
  - `backend/app/models/trip.py` (id, user_id, status, destination, start_date, end_date, group_size, budget_total, currency, constraints JSONB, pace, timestamps)
- **Tests:** `backend/tests/test_migrations.py` — apply migration on a temp DB, assert tables exist.

### Slice 1.2: Trip CRUD endpoints

- [x] **Done when:** `POST /trips` creates a Trip and returns its ID. `GET /trips/{id}` returns it. Pydantic validation rejects bad input. *(Landed as PR #6, squashed to a6c2aad; Beads `trip-concierge-glh` closed. Roundtrip + 422 + 404 covered.)*
- **Files to create:**
  - `backend/app/schemas/trip.py` (Pydantic)
  - `backend/app/routes/trips.py`
  - `backend/app/services/trip_service.py`
- **Tests:** `backend/tests/test_trips_routes.py` — happy path + 422 on invalid input.

### Slice 1.3: First CrewAI agent (Researcher only, hardcoded output)

- [x] **Done when:** Calling `crew.run(destination="Goa")` returns a list of 3 dummy destinations from the Researcher agent. No real LLM call yet — agent is stubbed to return fixtures. *(Landed as PR #8, squashed to 82d1a3a; Beads `trip-concierge-djm` closed. Agent role/goal/backstory verbatim from prompts.md §1.1.)*
- **Files to create:**
  - `agents/researcher.py` (CrewAI Agent definition, prompts from `agents/prompts.md`)
  - `agents/crew.py` (single-agent crew)
  - `tests/fixtures/researcher_output.json`
- **Tests:** `tests/test_researcher_stub.py` — assert structure of returned data.
- **Notes:** Read `agents/prompts.md` before this slice. Do not invent the agent's role/goal/backstory.

### Slice 1.4: Wire LLM into Researcher

- [x] **Done when:** Researcher actually calls Claude Sonnet 4 via Anthropic SDK and returns 3 real candidate destinations for a real input. Langfuse trace appears. *(Landed as PR #9, squashed to 81164cd; Beads `trip-concierge-1ex` closed. Live test verified: real Goan venues with Tavily-sourced URLs; trace `researcher.run` id `c166622d25c76f` in Langfuse cloud.)*
- **Files to create:**
  - `agents/tools/web_search.py` (Tavily wrapper)
  - `backend/app/config.py` (centralized env reading)
- **Tests:** `tests/test_researcher_live.py` — marked `@pytest.mark.live`, skipped in CI by default. Asserts response shape, not content.

---

## Phase 2 — Full crew, sequential process (Week 2, days 1-3)

### Slice 2.1: Local Expert agent

- [x] **Done when:** Local Expert runs after Researcher in sequential mode, narrows 3 destinations to 1 with rationale. *(Landed as PR #10, squashed to a36d2e5; Beads `trip-concierge-dkw` closed. Live test verified `why_this_not_that` field appears.)*
- **Files to create:** `agents/local_expert.py`
- **Tests:** sequential crew run produces both agents' outputs in order.

### Slice 2.2: Logistics Planner agent

- [x] **Done when:** Logistics produces a day-by-day itinerary with travel times for the chosen destination. Uses a maps tool stub for now. *(Landed as PR #12, squashed to fd3263e; Beads `trip-concierge-d7x` closed. Merged without CI green — Actions had a transient codeload.github.com 404 on `astral-sh/setup-uv` SHA; locally verified live + offline.)*
- **Files to create:** `agents/logistics.py`, `agents/tools/maps_stub.py`
- **Tests:** itinerary has the right number of days; each day has ordered blocks.

### Slice 2.3: Budget Auditor agent

- [x] **Done when:** Budget Auditor rejects plans that exceed budget and requests revision. Two-retry policy enforced. *(Landed as PR #13, squashed to 46123eb; followup fix 70600d1; Beads `trip-concierge-ge4` closed. Surgeon design — Auditor applies own cuts, orchestrator in crew.py runs up to MAX_AUDIT_PASSES=2 in Python. 5 pure-Python orchestration tests assert the loop deterministically.)*
- **Files to create:** `agents/budget_auditor.py`
- **Tests:** synthetic over-budget plan triggers exactly one revision; over-budget after retries surfaces a "couldn't fit" message.

### Slice 2.4: Day + Block + Source models and migrations

- [x] **Done when:** Crew output is persisted to Postgres as Day, Block, Source records linked to a Trip. *(Landed as PR #14, squashed to 67bc5fc; Beads `trip-concierge-dxd` closed. Also added AgentRun model + persist_audited_plan() service. CASCADE chain verified by test.)*
- **Files to create:**
  - `backend/app/models/day.py`
  - `backend/app/models/block.py`
  - `backend/app/models/source.py`
  - `backend/app/models/agent_run.py`
  - migration `0002_days_blocks_sources.py`
- **Tests:** crew run for a synthetic trip creates the expected row counts.

### Slice 2.5: `/trips/{id}/plan` endpoint — decomposed into 2.5a / 2.5b / 2.5c

The original Slice 2.5 spec ("p95 ≤ 30s for a small trip") was unrealistic — slice 2.3 live runs measured a 9-minute crew runtime, and gateway proxies (Fly.io, Hetzner Nginx defaults) time out at 60s. Decomposed after the architecture review into three slices that build up the production-correct shape: HTTP boundary between backend and agents (Option B done-right), with a Redis-backed arq job queue so the user-facing HTTP request returns in <1s. Layered on top is a uv workspace, purely for dev ergonomics + shared Pydantic types across backend/agents/mcp_server.

#### Slice 2.5a: agents as standalone FastAPI service + uv workspace

- [x] **Done when:** *(Landed as PR #15 squashed to ffb0a3f, across two commits — d78a24e refactor-only move to `src/trip_agents`, then 0a8ffb3 new wiring. Beads `trip-concierge-q9o` closed. Workspace conversion surfaced a real crewai transitive pin conflict; observation recorded in `experiments/01-langfuse.md`.)*
  - Root `pyproject.toml` declares `[tool.uv.workspace] members = ["backend", "agents"]`. **mcp_server joins in slice 3.1** when it gains a proper installable package layout — today it has only one source file with no internal imports, so deferring is cheaper than restructuring speculatively.
  - `uv sync` from repo root provisions all three projects (per-project sync still works).
  - `agents/` has a FastAPI service exposing `POST /run` that accepts a `TripRunRequest` and returns the `AuditedPlan` JSON.
  - A backend integration test calls the agents service via `httpx` (TestClient against the agents FastAPI app, mocked `crew.run`) and verifies the response validates as `trip_agents.schemas.AuditedPlan`.
  - Backend can `from trip_agents.schemas import …` via the workspace path.
  - `make dev`, `make test`, `make check` all work across the workspace.
- **Not in scope:** Redis, arq, job queue, status polling, AgentRun writes, backend's HTTP route to `/trips/{id}/plan`. Those are 2.5b/c.
- **Beads:** `trip-concierge-q9o`.

#### Slice 2.5b: Redis + arq job queue for crew runs

- [ ] **Done when:**
  - `redis` service added to `docker-compose.yml`.
  - `arq` pinned exact in both `backend/` and `agents/`.
  - `POST /trips/{id}/plan` on backend enqueues an arq job, returns **202 Accepted** with `{job_id, status_url}` in **< 1 second** (the user-facing latency target).
  - An arq worker (process launched alongside the agents service) consumes jobs, runs the 4-agent crew, calls `persist_audited_plan()`, and writes `AgentRun` rows with token counts, costs, and durations.
  - `make dev` (or new `make worker`) launches the worker.
  - Integration test (offline, mocked `crew.run`): enqueue → in-process worker drains queue → fetch trip and assert days/blocks persisted + AgentRun rows present.
  - CI: redis service container alongside postgres in `ci.yml`.
  - Langfuse traces include queue wait time as a distinct span.
- **Not in scope:** status polling endpoint (2.5c), cancellation, per-agent progress messages.
- **Beads:** `trip-concierge-odc` (blocked by 2.5a).

#### Slice 2.5c: Status endpoint + polling protocol

- [ ] **Done when:**
  - `GET /trips/{trip_id}/plan/status` returns `{state, progress_message, started_at, finished_at, error, trip_url}` where state ∈ {queued, running, done, failed}.
  - The arq worker updates `progress_message` before each agent kickoff: `"researching candidates"`, `"narrowing to best fits"`, `"building day-by-day plan"`, `"audit pass 1"`, `"audit pass 2"` (if reached).
  - `DELETE /trips/{trip_id}/plan` cancels an in-flight job: 204 on cancel, 404 if no job, 409 if already done. Cancelled jobs don't write AgentRun rows for incomplete passes.
  - Integration test: enqueue → poll three times → observe queued → running → done; last poll has `trip_url`.
  - Integration test: enqueue → cancel mid-flight → status reports `failed` with `error="cancelled by user"`.
  - OpenAPI docs at `/docs` show the status schema.
- **Not in scope:** SSE / websocket streaming (v2.0), email-on-complete, retry-on-failure.
- **Beads:** `trip-concierge-zyy` (blocked by 2.5b).

---

## Phase 3 — MCP server (Week 2, days 4-5)

### Slice 3.1: MCP server skeleton with auth

- [ ] **Done when:** Claude Desktop can connect to the MCP server. First call returns a magic-link URL. Clicking it issues a token. Subsequent calls use the token.
- **Files to create:**
  - `mcp_server/server.py`
  - `mcp_server/auth.py`
  - `mcp_server/tools/_base.py` (token verification decorator)
  - Magic-link route in `backend/app/routes/auth.py`
- **Tests:** unit tests for token issuance and verification. Manual test against Claude Desktop documented in `mcp_server/README.md`.

### Slice 3.2: `create_trip` MCP tool

- [ ] **Done when:** From Claude Desktop, "Plan me a 3-day Goa trip, ₹40k, chill vibe, no parties" creates a trip via MCP and returns a share URL. Uses the description string from `agents/prompts.md`.
- **Files to create:** `mcp_server/tools/create_trip.py`
- **Tests:** unit test calling the tool function directly with mocked backend.

### Slice 3.3: `get_trip`, `refine_trip`, `regenerate_day` MCP tools

- [ ] **Done when:** All three tools work end-to-end in Claude Desktop. `refine_trip` uses the hierarchical CrewAI process.
- **Files to create:** one file per tool under `mcp_server/tools/`
- **Tests:** unit + manual.

### Slice 3.4: `add_constraint`, `add_source`, `find_alternative`, `explain_recommendation` MCP tools

- [ ] **Done when:** All four tools work. `add_source` accepts a URL, fetches and parses it, attaches to trip with embedding.
- **Files to create:**
  - Tool files
  - `backend/app/services/source_ingestion.py` (URL fetch + parse + embed)
- **Tests:** source ingestion handles common formats (Reddit, blog, plain text).

### Slice 3.5: `share_trip`, `export_trip` MCP tools

- [ ] **Done when:** Tools return signed URLs that work. PDF export generates a usable file.
- **Files to create:** tool files, `backend/app/services/pdf_export.py`
- **Tests:** PDF generation produces a valid file with expected page count.

---

## Phase 4 — Web app (Week 3)

### Slice 4.1: Auth.js setup

- [ ] **Done when:** Email magic link and Google OAuth both work in dev. Sessions persist across page loads.
- **Files to create:** `web/app/api/auth/[...nextauth]/route.ts`, `web/lib/auth.ts`
- **Tests:** middleware test that protected routes redirect.

### Slice 4.2: Trip list and trip detail pages (server components)

- [ ] **Done when:** Logged-in user sees their trips at `/trips`. Clicking a trip opens `/trips/{id}` with day-by-day itinerary.
- **Files to create:** `web/app/trips/page.tsx`, `web/app/trips/[id]/page.tsx`, `web/lib/api.ts`
- **Tests:** rendering test with mocked API responses.

### Slice 4.3: Day card UI — mobile-first

- [ ] **Done when:** Day view renders correctly at 360px. Touch targets ≥ 44px. Sticky day chip nav. Swipe-to-lock and swipe-to-remove work.
- **Files to create:** `web/components/DayCard.tsx`, `web/components/BlockItem.tsx`, `web/components/DayNav.tsx`
- **Tests:** Playwright mobile-viewport test.

### Slice 4.4: Map view with MapLibre

- [ ] **Done when:** Map renders, pins show, tap-to-scroll-itinerary works. Two-column layout above 768px, hidden behind a toggle on mobile.
- **Files to create:** `web/components/MapView.tsx`
- **Tests:** screenshot test at mobile + desktop viewports.

### Slice 4.5: Constraint controls + pace slider

- [ ] **Done when:** Bottom-sheet UI for setting constraints. Changes trigger plan regeneration via backend.
- **Files to create:** `web/components/ConstraintSheet.tsx`, `web/components/PaceSlider.tsx`
- **Tests:** interaction tests.

### Slice 4.6: Edit and regenerate (block-level + day-level)

- [ ] **Done when:** Single-block regen works. Day regen works. Undo last change works. Locked blocks are preserved across regens.
- **Files to create:** `web/components/RegenerateMenu.tsx`, history stack utility
- **Tests:** lock preservation test.

### Slice 4.7: Source citations expansion + "why this was picked"

- [ ] **Done when:** Tapping a block expands to show source list, confidence indicator, and rationale.
- **Files to create:** `web/components/BlockDetail.tsx`, `web/components/ConfidenceBadge.tsx`
- **Tests:** expand/collapse interaction test.

### Slice 4.8: Visible agent activity panel

- [ ] **Done when:** Collapsible "How this plan was made" panel at the top of each day shows the agent activity from the `AgentRun` records.
- **Files to create:** `web/components/AgentActivity.tsx`
- **Tests:** rendering with mocked agent run data.

### Slice 4.9: Share + export UI

- [ ] **Done when:** Share button generates a link, copies to clipboard. PDF download works. WhatsApp share opens with formatted message.
- **Files to create:** `web/components/ShareMenu.tsx`
- **Tests:** clipboard write test, link generation test.

### Slice 4.10: PWA manifest, service worker, offline mode

- [ ] **Done when:** App is installable on iOS Safari and Android Chrome. Last-synced trip renders offline. Lighthouse mobile performance ≥ 85.
- **Files to create:** `web/app/manifest.ts`, `web/public/sw.js`, offline cache config
- **Tests:** Lighthouse CI assertion in pipeline.

---

## Phase 5 — Polish + deploy (Week 4)

### Slice 5.1: Hierarchical process for refinement

- [ ] **Done when:** `refine_trip` and complex multi-step edits use `Process.hierarchical` with a manager LLM. Logged traces show manager routing decisions.

### Slice 5.2: BYO research polish

- [ ] **Done when:** Pasting Reddit threads, YouTube URLs, and Google Maps lists all work. "From your sources" badge renders correctly.

### Slice 5.3: Memory enabled on crew

- [ ] **Done when:** CrewAI memory (short-term, long-term, entity) persists per user. User memory page in web app shows what's remembered with delete option.
- **Files to create:** `web/app/settings/memory/page.tsx`, `backend/app/routes/memory.py`

### Slice 5.4: Rate limiting + cost dashboard

- [ ] **Done when:** Per-user limits enforced (20/hr, 100/day). Internal `/admin/costs` page shows token usage by trip and agent.

### Slice 5.5: Production deploy

- [ ] **Done when:** Backend on Fly.io or Hetzner, web on Vercel, Postgres + Redis managed. Domain `tripconcierge.app` resolves. MCP server publicly reachable. End-to-end test passes against production.

### Slice 5.6: v1.0 release checklist

- [ ] All tests passing in CI
- [ ] Lighthouse mobile ≥ 85
- [ ] All MCP tools tested in Claude Desktop
- [ ] No package on the denylist in lockfile
- [ ] `make check` clean
- [ ] `docs/prd.md` Definition of Done passes manually

---

## After v1.0

v2.0 roadmap lives in `docs/prd.md` Appendix A. Don't start v2.0 work until v1.0 is shipped and stable for 14 days.

---

_Last updated: 2026-05-24_
