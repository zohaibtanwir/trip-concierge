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

- [x] **Done when:** Crew output is persisted to Postgres as Day, Block, Source records linked to a Trip. *(Landed as PR #14, squashed to 67bc5fc; Beads `trip-concierge-dxd` closed. Also added AgentRun model + persist_audited_plan() service. CASCADE chain verified by test. AgentRun model was later replaced by JobRun in slice 2.5b — see migration 0004.)*
- **Files to create:**
  - `backend/app/models/day.py`
  - `backend/app/models/block.py`
  - `backend/app/models/source.py`
  - `backend/app/models/agent_run.py` *(replaced by `job_run.py` in slice 2.5b)*
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
- **Not in scope:** Redis, arq, job queue, status polling, JobRun writes, backend's HTTP route to `/trips/{id}/plan`. Those are 2.5b/c.
- **Beads:** `trip-concierge-q9o`.

#### Slice 2.5b: Redis + arq job queue for crew runs

- [x] **Done when:** *(Landed as PR #16 squashed to 56feeff, across three commits: b05096a queue infrastructure, 6268aba post-housekeeping, 075e152 backend POST /trips/{id}/plan wiring. Beads `trip-concierge-odc` closed. Real `_is_retryable` HTTPStatusError money-leak bug caught by pure-function test before commit; real `_REPO_ROOT` silent breakage from slice-2.5a src-layout move fixed incidentally. Observations recorded in `experiments/01-langfuse.md`.)*
  - `redis` service added to `docker-compose.yml`.
  - `arq` pinned exact in both `backend/` and `agents/`.
  - `POST /trips/{id}/plan` on backend enqueues an arq job, returns **202 Accepted** with `{job_id, status_url}` in **< 1 second** (the user-facing latency target).
  - An arq worker (process launched from `make backend.worker` — worker lives in backend, not agents, because it needs DB access) consumes jobs, runs the 4-agent crew, calls `persist_audited_plan()`, and writes **one** `JobRun` row per job (success/failed/cancelled). Per-agent observability comes from `JobRun.agent_summary` (JSONB populated via CrewAI's step_callback) — not per-agent rows. v2.0 question if we ever need finer grain.
  - `make dev` (or new `make worker`) launches the worker.
  - Integration test (offline, mocked `crew.run`): enqueue → in-process worker drains queue → fetch trip and assert days/blocks persisted + JobRun row present.
  - CI: redis service container alongside postgres in `ci.yml`.
  - Langfuse traces include queue wait time as a distinct span.
- **Not in scope:** status polling endpoint (2.5c), cancellation, per-agent progress messages.
- **Beads:** `trip-concierge-odc` (blocked by 2.5a).

#### Slice 2.5c: Status endpoint + polling protocol

- [ ] **Done when:**
  - `GET /trips/{trip_id}/plan/status` returns `{state, progress_message, started_at, finished_at, error, trip_url}` where state ∈ {queued, running, done, failed}.
  - The arq worker updates `progress_message` before each agent kickoff: `"researching candidates"`, `"narrowing to best fits"`, `"building day-by-day plan"`, `"audit pass 1"`, `"audit pass 2"` (if reached).
  - `DELETE /trips/{trip_id}/plan` cancels an in-flight job: 204 on cancel, 404 if no job, 409 if already done. Cancelled jobs write a JobRun row with status=cancelled and whatever agent_summary the step_callback captured before cancellation.
  - Integration test: enqueue → poll three times → observe queued → running → done; last poll has `trip_url`.
  - Integration test: enqueue → cancel mid-flight → status reports `failed` with `error="cancelled by user"`.
  - OpenAPI docs at `/docs` show the status schema.
- **Not in scope:** SSE / websocket streaming (v2.0), email-on-complete, retry-on-failure.
- **Beads:** `trip-concierge-zyy` (blocked by 2.5b).

---

## Phase 3 — MCP server (Week 2, days 4-5)

### Slice 3.1: MCP server skeleton with auth

- [ ] **Done when:** Claude Desktop can connect to the MCP server. First call (with no token on disk) returns dev-CLI instructions for obtaining a token. Once the token is stored at `~/.config/trip-concierge/token`, subsequent calls authenticate via the `x-tc-token` header. The production clicked-link / magic-link flow is **deferred to slice 4.1**; 3.1 ships dev-only auth via the `tc-issue-mcp-token` CLI to unblock 3.2-3.5.
- **Files created (refactor commit):** `mcp_server/src/trip_mcp/` (src-layout move, joins uv workspace).
- **Files created (auth commit):**
  - Backend: `app/services/mcp_tokens.py` (JWT issue/verify), `app/auth/dependencies.py` (`require_mcp_token`), `app/routes/auth.py` (`GET /auth/mcp/me`), `app/cli/issue_mcp_token.py` (CLI).
  - MCP: `src/trip_mcp/{config,auth,http_client}.py`, `src/trip_mcp/tools/_base.py` (`@requires_auth`), `README.md` (manual Claude Desktop recipe).
- **Tests:** 10 backend (JWT roundtrip + bad-sig + expired + malformed + CLI + 3× route auth states), 6 mcp_server (4 storage + 2 tool-base). Manual test against Claude Desktop documented in `mcp_server/README.md`.

### Slice 3.2: `create_trip` MCP tool

- [ ] **Done when:** From Claude Desktop, "Plan me a 3-day Goa trip, ₹40k, chill vibe, no parties" creates a trip via MCP and returns a share URL. Uses the description string from `agents/prompts.md`.
- **Files to create:** `mcp_server/tools/create_trip.py`
- **Tests:** unit test calling the tool function directly with mocked backend.

### Slice 3.3: `get_trip`, `refine_trip`, `regenerate_day` MCP tools

- [ ] **Done when:** All three tools work end-to-end in Claude Desktop. `refine_trip` uses the hierarchical CrewAI process.
- **Files to create:** one file per tool under `mcp_server/tools/`
- **Tests:** unit + manual.

### Slice 3.4 — split into 3.4a + 3.4b

The original entry bundled all four tools. Split on 2026-05-29 per the modification-vs-context axis. Pair tools sharing a structural pattern get written and reviewed together (description-corpus discipline from slice 3.3's marsh observation). add_source's v1.0 scope (URL fetch only / + embedding / + per-site parsers) is a substantial design decision in its own right and deserves a focused session, not a passing call inside a four-tool slice.

#### Slice 3.4a: `add_constraint` + `find_alternative` MCP tools

- [ ] **Done when:** Both tools work in Claude Desktop. `add_constraint` appends to Trip.constraints and enqueues a refine job. `find_alternative` returns 3 alternatives for one block with rationales.
- **Tools share structural pattern:** both modification tools, both feed into trip changes via the slice-3.3 active-job pattern (where applicable), both carry the prohibition discipline against "applied/done/ready" claims.
- **Tests:** unit per tool + integration. Mocked-LLM only; manual Claude Desktop validation post-merge.
- Ticket: `trip-concierge-9p7`.

#### Slice 3.4b: `add_source` + `explain_recommendation` MCP tools + `source_ingestion` service

- [ ] **Done when:** Both tools work. `add_source` accepts a URL, fetches and parses it, attaches to trip (with embedding per scope decision below). `explain_recommendation` returns sources + rationale for a Block.
- **Tools share structural pattern:** both context tools, both surface or attach research, both compete in routing against `web_search`, both carry the fabrication-prohibition language.
- **Open scope decision for slice opening:** add_source v1.0 has three levels — fetch-only (v1.0a), + pgvector embedding (v1.0b), + per-site parsers (v1.0c). BUILD_PLAN's "URL fetch + parse + embed" implies v1.0b minimum.
- **Files to create:**
  - Tool files
  - `backend/app/services/source_ingestion.py` (URL fetch + parse + embed depending on chosen v1.0 level)
- **Tests:** source ingestion handles common formats (Reddit, blog, plain text); pgvector embedding round-trip.
- Ticket: `trip-concierge-5bw`. Blocked-by `trip-concierge-9p7` so the two slices ship sequentially.

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

### Slice 4.1b: MCP-side magic-link challenge

- [ ] **Done when:** MCP server with `TC_MCP_USER_EMAIL` configured but no token completes the full flow on first tool call: POST `/auth/mcp/challenge` → user clicks email link → GET `/auth/mcp/redeem` renders success HTML → next tool call's poll retrieves the JWT, MCP server saves to disk, tool succeeds.
- **Tracked as:** `trip-concierge-0h0` (P1, blocks none).
- **Files created:** `backend/app/services/mcp_challenges.py`, `backend/app/services/resend_send.py`, `backend/app/models/auth_challenge.py`, `backend/app/rate_limit.py`, `backend/app/db/migrations/versions/0009_auth_challenges.py`, `mcp_server/src/trip_mcp/challenges.py`.
- **Files modified:** `backend/app/routes/auth.py` (3 new endpoints + slowapi decorators), `mcp_server/src/trip_mcp/{http_client,config,tools/_base}.py` + 10 tool files (replace `_DEV_CLI_HINT` with challenge flow).
- **Tests:** 31 new backend + 8 net new mcp_server tests; 4 mcp_server tool tests renamed.
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.2: Trip list and trip detail pages (server components)

- [x] **Done when:** Authenticated users can view a list of their own trips (state-badged per derived state from latest plan JobRun + Redis active-job overlay), click through to a trip detail page that renders day-by-day blocks for succeeded trips, planning progress for in-flight trips, error message for failed trips, and "hasn't been planned yet" fallback for genuinely-unplanned trips. Ownership enforced at backend route level via 403 on cross-user access.
- **Tracked as:** `trip-concierge-2th` (P1, blocks 4.3/4.4).
- **Files created:**
  - backend: 1 new route (`/internal/trips/{id}/active-job` Redis probe), 2 new test files (`test_trip_list_route.py`, `test_trip_ownership.py`, `test_internal_active_job.py`).
  - web: 2 new RSC pages (`app/trips/page.tsx`, `app/trips/[id]/page.tsx`), 4 new components (`state-badge`, `trip-block`, `trip-day`, `trip-list-row`), 4 new test files (`backend.test.ts`, `trip-list.test.tsx`, `trip-detail.test.tsx`, `trip-row-and-day.test.tsx`).
- **Files modified:**
  - backend: `routes/trips.py` (ownership checks + list endpoint + internal active-job route), `services/trip_service.py` (Postgres+Redis dual-read), `schemas/trip.py` (TripListItem + TripListResponse), `models/trip.py` (DEPRECATED docstring on `status`), `main.py` (router registration).
  - web: `lib/backend.ts` (added `fetchTripList` + `fetchTripDetail` + `BackendError`).
- **Tests:** 14 new backend (11 from commit 1 + 3 from active-job route) + 25 new web = 39 net slice tests. Full suite (backend 192 + mcp_server 99 + agents 45 + web 39) = 375.
- **Followup tickets filed:** `trip-concierge-id4` (drop dead `Trip.status` column), `e4v` (shadcn-ui pre-4.3), `og1` (loading/error.tsx pre-4.3), `hia` (extend `JobRun.status` enum to eliminate Redis dual-read), `29l` (distinguish rejected/failed UX in Phase 5), `req` (vitest auto-cleanup config), `pdo` (narrow `except Exception` in `_planning_trip_ids`), `jv7` (force-dynamic build-time guard).
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.3: Day card UI — mobile-first

- [x] **Done when:** Trip Concierge design spec v1.0 landed (`docs/design-spec.md` + 4 voyage-elite reference HTMLs). Tailwind v4 theme tokens via CSS-first `@theme` config, Google Fonts + Material Symbols wired, shadcn-ui scaffolded with Button + Sheet + Dialog. 4 slice-4.2 components migrated to spec §14 patterns (state-badge §3.6 palette, trip-day numbered-circle vertical timeline §9.5, trip-block Material Symbols by type, trip-list-row active-teal-glow + focus-visible:ring). Trip detail page two-column layout §9.2 with sticky day chip timeline + "How this plan was made" panel rendering agent activity from JobRun.agent_summary (PRD §F8 partial). Plan-again Dialog confirms full replan on failed trips via planAgainAction Server Action.

- ⚠️ **PRD §F2 partial compliance:** Slice 4.3 ships visual scaffolding only. Block expand-on-tap wrapper (`BlockExpand`) exists but is not wired to block clicks — wiring lands with refine UX in slice 4.5/4.6. Gesture behaviors (swipe-left removes + swipe-right locks + 5s undo + locked-block schema) bundled into `trip-concierge-0hi` for the same slice. v1.0a release criteria include explicit §F2 review at Phase 5 closeout.

- **Tracked as:** `trip-concierge-d74` (P1, blocks 4.4/4.5/4.6).
- **Files created:**
  - docs: `design-spec.md` (spec v1.0, 17 sections); `design-references/voyage-elite-{explore,itinerary,booking,profile}.html` (4 reference screens).
  - web (components): `components/ui/{button,sheet,dialog}.tsx` (shadcn primitives); `components/{block-detail,block-expand,day-chip-timeline,plan-history-panel,plan-again-dialog}.tsx` (5 new components); `components.json` + `lib/utils.ts` (shadcn config + cn helper).
  - web (server action): `lib/actions.ts` (planAgainAction).
  - web (tests): `tests/{theme-setup,ui-button,ui-sheet,ui-dialog,actions,block-expand,day-chip-timeline,plan-again-dialog,plan-history-panel}.test.{ts,tsx}` (9 new test files).
- **Files modified:**
  - backend: `schemas/plan.py` (agent_summary field), `routes/plan.py` (populate from latest JobRun), `tests/test_plan_status.py` (3 new assertions).
  - web (theme): `app/globals.css` (Tailwind v4 @theme block per spec §13 + §13.1 custom CSS); `package.json` (exact-pinned shadcn deps; lucide-react removed); `pnpm-workspace.yaml` (msw ignored builds); `biome.json` (components/ included, globals.css excluded per Tailwind v4 parser gap — see `trip-concierge-ydi`).
  - web (components): `components/{state-badge,trip-list-row,trip-day,trip-block}.tsx` (spec §14 migration).
  - web (pages): `app/trips/page.tsx` (sticky glass header + typography tokens); `app/trips/[id]/page.tsx` (two-column layout + sticky right panel + Plan again wiring).
  - web (tests): `tests/{trip-detail,trip-row-and-day,backend}.test.{ts,tsx}` (new assertions + token-migration source-reads).
- **Tests:** 22 net new slice tests (3 backend agent_summary + 19 web: theme-setup 26 + 3 shadcn smokes + new component tests + token-migration reads + integration assertions). Cumulative repo total: 428 (backend 195 + mcp_server 99 + agents 45 + web 89).
- **Followup tickets filed:**
  - Spec scope: `trip-concierge-auu` (v1.1 patterns), `0hi` (§F2 gesture compliance debt bundled), `gco` (backend block enrichment).
  - Server actions: `u8v` (object-args refactor for planAgainAction + future actions).
  - Tooling: `ydi` (Biome CSS-parser re-eval when 2.5+ ships).
  - Closed in this slice: `e4v` (shadcn-ui pre-4.3) — install landed in commit 1.
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.4: Map view with MapLibre

- [x] **Done when:** MapLibre map panel renders on `/trips/[id]` succeeded + failed states (stacks between DayChipTimeline and PlanHistoryPanel in the sticky right rail). Destination-centered view with single pin + always-open Popup labeled `{N} day(s) in {City}`. OpenFreeMap demo tiles via env-overridable `MAPLIBRE_TILE_URL`. Auth-gated Playwright fixture (`p8l`) landed as commit 1 — consumed by slice 4.4's map smoke + all future visual-heavy slices.

- ⚠️ **PRD §F3 architectural foundation only.** The map surface exists for v1.0b pins to land into; user-visible §F3 acceptance criteria are NOT yet met. Specifically NOT shipped: per-block pins (deferred to backend lat/lng work — `trip-concierge-423`), route lines between blocks (deferred to Directions API slice — `trip-concierge-kue`), day color-coding, "Today" mode, tap-pin-to-scroll. What ships: destination-centered map panel with pin + label, attribution, sticky placement, mobile collapse. v1.0a release criteria include explicit §F3 review at Phase 5 closeout (joining §F2 review from slice 4.3).

- **What this slice delivers:**
  - **Engineering value (high):** auth-gated Playwright fixture (JWE storageState — consumed by all future visual slices), deterministic e2e test seed (canonical visual fixture for slice 4.4+), MapLibre architectural foundation, spec §9.12 + §17.11.
  - **User-visible value (modest):** map shows destination context only; per-block pins land when v1.0b backend lat/lng work completes (`trip-concierge-423`).

- **Tracked as:** `trip-concierge-o9r` (P1, blocks 4.5/4.6 once map progresses).
- **Files created:**
  - web: `lib/destination-coords.ts`, `components/trip-map.tsx`, `scripts/mint-playwright-auth.ts`, `scripts/seed-e2e-trip.ts`, `tests/lib-destination-coords.test.ts`, `tests/trip-map.test.tsx`, `tests/e2e/auth-fixture-smoke.spec.ts`, `tests/e2e/slice-4.4-map.spec.ts`.
- **Files modified:**
  - docs: `design-spec.md` (§9.12 + §17.11 + v1.0.1 changelog).
  - web: `app/trips/[id]/page.tsx` (TripMap integration), `lib/env.ts` (`MAPLIBRE_TILE_URL`), `package.json` (exact-pinned `maplibre-gl`, `react-map-gl`, `@panva/hkdf`, `jose`, `tsx`), `pnpm-workspace.yaml` (esbuild build-script block), `playwright.config.ts` (chromium-authed project), `.gitignore` (playwright-auth.json).
  - CI: `.github/workflows/ci.yml` — added 5 env vars (NEXTAUTH_SECRET, NEXTAUTH_URL, TC_MCP_TOKEN_SECRET, INTERNAL_AUTH_SECRET, BACKEND_URL) as foundation for future auth-gated Playwright CI orchestration. Foundation only; CI workflow steps to consume them tracked as `trip-concierge-0y8`.
- **Tests:** 14 net new (2 backend in commit 1 fixture smoke + 7 vitest unit in commit 2 + 5 Playwright e2e in commit 2). Cumulative: 446 (195 backend + 99 mcp_server + 45 agents + 102 web vitest + 5 e2e new + commit 1's 2 + existing 4 from slice 4.3).
- **Followup tickets filed:**
  - `trip-concierge-423` (P2): Backend lat/lng population for v1.0b per-block pins (crew prompts + geocoding).
  - `trip-concierge-dj0` (P3): Production MapLibre tile source decision (Stadia / MapTiler / self-host).
  - `trip-concierge-kue` (P3): PRD §F3 v1.0b — route lines + day color-coding + tap-pin-to-scroll + "Today" mode + Directions API.
  - `trip-concierge-0y8` (P2): CI orchestration for auth-gated Playwright tests (consumes the env vars commit 1 added; wires the workflow steps).
  - `trip-concierge-auu` (P3, updated): bundles spec v1.1 prep notes from this slice (§17.11 transitions for pin-less → pinned migration).
- **Tickets closed in this slice:**
  - `trip-concierge-p8l`: Auth-gated Playwright fixture (closed at commit 1).
  - `trip-concierge-w87`: TripMap editorial-shadow clipping concern (closed as superseded by Q22 resolution in commit 3 — TripMap now uses `border-outline-variant` only, matching right-rail consistency).
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.5: Constraint controls (4 of 8 §F4 kinds)

- [x] **Done when:** Constraint editor renders on `/trips/[id]` right rail between TripMap and PlanHistoryPanel — third Phase 4 slice to ship a PRD-feature surface (§F2 in 4.3 → §F3 in 4.4 → §F4 in 4.5). Four kinds wired: dietary (multi-select chips), mobility (radio), accessibility (toggle), no-go (free-text list). Submit fires `POST /trips/{id}/constraints` via `addConstraintAction` Server Action — slice 3.4a endpoint auto-enqueues `refine_trip` on success. Read-only chip list (Material Symbols per kind) renders persisted `trip.constraints.rules[]` below the editor.

- ✅ **PRD §F4 partial compliance — discharged in slice 4.5b (`trip-concierge-cdr`).** Slice 4.5 shipped the rules-shaped 4 (dietary, mobility, accessibility, no-go). Slice 4.5b shipped the settings-shaped 2 (pace, total budget via new `PATCH /trips/{id}` route) + the remaining rules-shaped 2 (walking_limit, per-day budget as new ConstraintForm sections) + Budget Auditor enforcement loop wiring in `refine_trip`. §F4 is fully discharged in v1.0a — no Phase 5 review gate remaining on this PRD section. The historical "partial → discharged" timeline is preserved in spec §17.12 for the architectural-foresight narrative.

- **What this slice delivers:**
  - **User-visible value (high):** the first interactive control surface on the trip detail page that produces a re-plan. Establishes the "Save and re-plan" → "Saving…" → restored plan pattern that slice 4.6 (edit/regenerate) will inherit.
  - **Engineering value (modest):** `forceVariant` responsive-wrapper pattern proved out a second time (mirror of slice 4.3 BlockExpand); per-kind synthesizer discipline (`accessibility` framing branch) sets the pattern for the deferred caps. Spec §9.13 + §17.12.

- **Tracked as:** `trip-concierge-z9o` (P1).
- **Files created:**
  - web: `components/constraint-form.tsx`, `components/constraint-panel.tsx`, `components/constraint-list.tsx`, `tests/constraint-form.test.tsx`, `tests/constraint-panel.test.tsx`, `tests/constraint-list.test.tsx`, `tests/e2e/slice-4.5-constraints.spec.ts`.
- **Files modified:**
  - backend: `app/routes/constraints.py` (`accessibility` added to `ConstraintKind` Literal + per-kind synthesizer discipline comment), `app/services/constraint_synthesizer.py` (`_framing_for_kind` accessibility branch), `tests/test_constraints_endpoint.py` (new test for accessibility kind).
  - web: `lib/actions.ts` (`addConstraintAction` object-args Server Action + `AddConstraintResult` + `ConstraintKind` re-export + planAgainAction asymmetry note), `app/trips/[id]/page.tsx` (right-rail integration), `playwright.config.ts` (regex generalized to `/auth-fixture-smoke|slice-4\.\d/` — matches all Phase 4 specs without per-slice config changes).
  - docs: `design-spec.md` (§9.13 + §17.12 + v1.0.2 changelog).
- **Tests:** 23 net new (5 backend in commit 1 + 7 vitest unit in commit 2 + 2 Playwright e2e in commit 2 + 9 wrapper tests across 3 component test files). Cumulative: 469 (196 backend + 99 mcp_server + 45 agents + 111 web vitest + 7 chromium-authed e2e + 11 from prior).
- **Followup tickets filed:**
  - `trip-concierge-cdr` (P1): v1.0a-companion — pace slider + total/per-day budget caps + walking-distance slider + Budget Auditor enforcement loop wiring (§F4 bullets 2/3/4).
  - `trip-concierge-hr2` (P3): DELETE `/trips/{id}/constraints/{rule_idx}` endpoint + ConstraintList chip removal UI.
  - `trip-concierge-gdm` (P3, pre-existing): `useMediaQuery` runtime resolution for ConstraintPanel `forceVariant` (currently inline-only on page).
  - `trip-concierge-xcs` (P2, pre-existing): Web trip creation positioning decision — v1.0a deliberately defers web-side trip creation in favor of MCP-first narrative (Claude Desktop creates, PWA manages). Tracked for v1.0b reconsideration.
- **Tickets closed in this slice:**
  - `trip-concierge-z9o`: Constraint controls (closed at merge).
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.5b: PRD §F4 discharge — pace + budgets + walking-limit + auditor enforcement loop

- [x] **Done when:** All 8 PRD §F4 controls ship in v1.0a. Pace + total budget land as column writes via new `PATCH /trips/{id}` route (+ refine enqueue); per-day budget + walking-limit land as new sections in ConstraintForm using the existing slice-3.4a endpoint. Budget Auditor enforcement loop wired into `refine_trip` via `MAX_REFINE_AUDIT_PASSES = 2` Python orchestration (mirror of plan_trip's `MAX_AUDIT_PASSES` — PRD §F4 bullet 2 "max 2 retries" now holds for refine the same way it holds for initial plan).

- ✅ **§F4 fully discharged.** No Phase 5 review gate remaining on this PRD section.

- **What this slice delivers:**
  - **User-visible value (high):** the demo's load-bearing surface — Marsh narrative now reads "I changed pace from balanced to packed and the trip regenerated with more blocks per day," not "we're partially compliant with §F4." Settings-vs-rules ontology surfaced at three layers (data column vs JSONB array → API PATCH vs POST → UI "Update" vs "Save" verb) and codified in spec §9.14.
  - **Engineering value (substantial):** trip-lock helpers extracted to `services/trip_lock.py` (5 sibling-route importers swept + 3 duplicate `_ACTIVE_JOB_KEY_TTL_SECONDS = 900` constants removed); `_serialize_trip_for_crew` now flattens `per_day_budget` + `max_walking_km` from `constraints.rules[]` so the auditor sees real values instead of "unspecified"; `crew.refine()` now honors `MAX_REFINE_AUDIT_PASSES = 2` in code; prompts.md §3.5 corrective edit breaks the implicit "keep going until approved" signal that hierarchical refine could have spun on.

- **Tracked as:** `trip-concierge-cdr` (P1).
- **4-commit decomposition:**
  1. `4c7eb9b` — backend refactor + PATCH route + audit loop (22 tests). Extract `trip_lock`; new `routes/trip_settings.py`; serializer extraction; `MAX_REFINE_AUDIT_PASSES` + `_run_refine_audit_pass`; prompts.md §3.5 edit.
  2. `0a4fb73` — web PlanControlsPanel + `updateTripSettingsAction` (9 vitest + 3 e2e). Three-layer verb-as-disclosure ("Update settings and re-plan").
  3. `6648af2` — walking_limit + per-day budget sections in ConstraintForm (3 tests). Rules-shaped companions to commit 2's settings-shaped surface.
  4. `<commit-4-sha>` — docs (spec §9.13 + §9.14 + §17.12 + BUILD_PLAN + v1.0.2 → v1.0.3 bump).
- **Files created:**
  - backend: `app/services/trip_lock.py`, `app/routes/trip_settings.py`, `tests/test_trip_lock.py`, `tests/test_patch_trip_route.py`, `tests/test_refine_audit_constraints.py`.
  - agents: `tests/test_refine_audit_loop.py`.
  - web: `components/plan-controls-form.tsx`, `components/plan-controls-panel.tsx`, `tests/plan-controls-form.test.tsx`, `tests/plan-controls-panel.test.tsx`, `tests/e2e/slice-4.5b-plan-controls.spec.ts`.
- **Files modified:**
  - backend: `app/routes/plan.py`, `app/routes/alternative.py`, `app/routes/constraints.py`, `app/routes/refine.py`, `app/routes/regenerate.py`, `app/routes/sources.py` (all swept to import from `trip_lock`), `app/main.py` (`trip_settings` router), `app/worker.py` (`_extract_settings_from_rules` + serializer wiring).
  - agents: `src/trip_agents/crew.py` (`MAX_REFINE_AUDIT_PASSES`, `_run_refine_audit_pass`, refine audit loop), `src/trip_agents/tasks.py` (refine_task corrective edit), `prompts.md` §3.5.
  - web: `lib/actions.ts` (`updateTripSettingsAction` + `TripPace`), `components/constraint-form.tsx` (walking_limit + per-day budget sections), `app/trips/[id]/page.tsx` (PlanControlsPanel insertion), `tests/actions.test.ts` (3 new), `tests/constraint-form.test.tsx` (3 new).
  - docs: `design-spec.md` (§9.13 extended 4→6 sections, §9.14 NEW PlanControlsPanel, §17.12 rewritten as discharged historical note, v1.0.3 changelog).
- **Tests:** 37 net new (22 backend/agents + 9 web + 3 e2e queued + 3 web). Cumulative: **506** = 213 backend + 99 mcp_server + 52 agents (+1 skipped) + 123 web vitest + 7 chromium-authed e2e + 12 from prior (slice 4.5's 11 + slice 4.5b's 1 not-yet-merged e2e budget).
- **Followup tickets filed:**
  - `trip-concierge-6e2` (P3): Audit form-section visual redundancy — sr-only vs visible legends across ConstraintForm + PlanControlsForm + future settings forms. Surfaced when commit 2's vitest selector required disambiguation on the inline panel's "Pace" string.
- **Tickets closed in this slice:**
  - `trip-concierge-cdr`: Slice 4.5b (closed at merge).
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.5c: Application shell + web trip creation (discharge of two Sunday-smoke product gaps)

- [x] **Done when:** Two product gaps surfaced at Sunday-morning manual UI smoke (2026-06-07) are discharged in v1.0a — (1) application shell debt accumulated invisibly across 8 Phase 4 feature-axis slices (no header, no landing page, no new-trip CTA, no empty state, no profile/logout), and (2) Claude Desktop dependency was forced as the sole trip-creation path. Slice 4.5c ships: shared auth-aware `<Header />` (teal `bg-primary-container`, wordmark + profile menu with email + Sign out), full landing page at `/` (Hero with "Plan a trip" branched CTA + How it works + Why agents + Footer), two-paths `<NewTripDialog />` (Create here form via `createTripAction` two-call POST /trips → POST /trips/{id}/plan + Create in Claude Desktop tab), theme sentinels migrated from `/login` to root layout, `← All trips` back link relocated from trip detail's inline header to page body.

- ✅ **Two product gaps discharged in the same session arc** — reactive discharge per the slice-arc-blind-spots observation. Sunday smoke caught both; both shipped within hours rather than deferring to v1.0b. The methodological learning is documented in spec §17.13 (Application shell ownership pattern — non-feature-axis budget).

- **What this slice delivers:**
  - **Marsh demo answer-readiness (high):** Tim Bennett asking "what if I don't have Claude Desktop?" now has an honest answer (web form, friction-free path). Tim asking "where's the landing page?" sees a credible product surface, not a placeholder h1.
  - **User-visible value (substantial):** every authed route has a consistent teal sticky-glass header with profile menu + Sign out. Landing page exists. Trip creation is first-class web functionality, not MCP-gated.
  - **Engineering value (moderate):** shared `<Header />` extracts DRY violation across `/trips` + `/trips/[id]` inline headers. Theme sentinels move to root layout (single source of truth). Spec §9.16 + §17.13 codify the application-shell-vs-feature distinction for future readers.

- **Tracked as:** `trip-concierge-8yb` (P1).

- **5-commit decomposition (slice 4.5c proper):**
  1. `c984c48` — Shared `<Header />` extraction + theme sentinels migrated to root layout + `← All trips` moved to page body. 5 vitest tests for Header. trip-detail + trip-list tests updated with `vi.mock("@/components/header")` for nested-async-RSC.
  2. `53b76f9` — Landing page (Hero / How it works / Why agents / Footer) + teal navbar restyle (`bg-primary-container` + `text-on-primary-container`). 5 vitest tests for LandingPage.
  3. `385af1b` — `<NewTripDialog />` MCP-only (native `<dialog>` + showModal, prompt template, copy-to-clipboard, claude.ai/download). Top-right CTA + empty-state button (Q6=A consolidation). 5 vitest tests.
  4. `4c52f7c` — Two-paths reframe (commit 3.5). `createTripAction` Server Action (two-call: POST /trips → POST /trips/{id}/plan), `<NewTripForm />` (destination required + 6 optional fields, no vibe per architecture), dialog restructured as tabs (Create here default | Create in Claude Desktop), Hero "Plan a trip" CTA, `/trips?new=true` auto-open. 14 net new tests.
  5. `<commit-4-sha>` — Docs (spec §9.16 + §17.13 + v1.0.5 changelog) + stale-caveat copy swap on MCP tab + this BUILD_PLAN entry.

- **Bonus repair commits on main during the session arc** (not in slice 4.5c proper, but transparently listed here because they were surfaced by smoke during this slice work):
  - `7577e7c` — `web/scripts/mint-session-cookie.ts` dev utility (slice 4d0 close-out smoke surfaced unconfigured auth providers; this script lets dev/smoke proceed by minting Auth.js JWE cookies for any user).
  - `8baefb3` — PlanHistoryPanel `agent_summary` schema mismatch fix (slice 4.3 fixture used pre-qek-a shape; backend ships qek-a shape; 11 rows of `undefinedms` in production despite 506 passing tests) + ConstraintPanel currency threading (USD-on-INR bug on the Coorg trip).
  - `d93b03b` — `AgentSummaryRow` refactored to TypeScript discriminated union + shared fixtures module + design-spec.md §9.15 summary-row pattern (callback_summary heterogeneity from AgentFinish; third stale fixture caught during audit at N=3).
  - `55057f6` — `_formatTime` made date-context-aware ("Yesterday · HH:MM:SS" / "Sat · HH:MM:SS" / "Jun 6 · HH:MM:SS") + 4 new vitest cases via `vi.setSystemTime`.
  - `1ecdfea` (pre-arc) — Langfuse SDK v4 `environment` kwarg fix for trace partitioning.
  - `80dabb6` (pre-arc) — `.claude/rules/slice-completion-discipline.md` step 5b-1 formalization (archive any long-lived service log before kill in Step 5b).
  - `2e4ef72` (pre-arc) — repoint dupe ticket IDs (5gf→gdm, wce→xcs).

- **Files created (slice 4.5c proper):**
  - web: `components/header.tsx`, `components/landing-page.tsx`, `components/new-trip-dialog.tsx`, `components/new-trip-form.tsx`, `tests/header.test.tsx`, `tests/landing-page.test.tsx`, `tests/new-trip-dialog.test.tsx`.
- **Files modified (slice 4.5c proper):**
  - web: `app/layout.tsx` (theme sentinels migrated in), `app/login/page.tsx` (sentinels removed), `app/page.tsx` (placeholder → Header + LandingPage composition), `app/trips/page.tsx` (Header + NewTripDialog integration + ?new=true searchParam wiring), `app/trips/[id]/page.tsx` (Header integration + `← All trips` moved to page body), `lib/actions.ts` (`createTripAction` added), `tests/actions.test.ts` (3 new), `tests/smoke.test.tsx` (updated for nested-async-RSC pattern), `tests/trip-detail.test.tsx` (Header mock added), `tests/trip-list.test.tsx` (Header mock + searchParams pass-through), `tests/e2e/slice-4.3-smoke.spec.ts` (comment update to reflect layout-level sentinel home).
  - docs: `design-spec.md` (§9.16 NEW + §17.13 NEW + v1.0.5 changelog).

- **Tests:** 29 net new across slice 4.5c proper (5 Header + 7 LandingPage + 14 NewTripDialog two-paths + 3 createTripAction). Plus 4 from the date-formatter bonus commit. Cumulative across the session arc (slice 4d0 close + 4.5c): **153 web vitest** (a +21 over slice 4d0's 132 baseline) on the web side; backend/agents/mcp_server unchanged at 213 + 99 + 52 (+1 skipped).

- **Followup tickets filed during slice 4.5c:**
  - `trip-concierge-mb6` (P3): Investigate Auth.js cookie parsing crash on `/` under fresh headless Chromium. Slice 4.3 author noted at e2e probe site; commit 1 kept the `/login` workaround. Real fix would let probes route to `/`.
  - `trip-concierge-nhm` (P2, slice 4d0 carryover): Enrich `agent_summary` events with `agent_role` field — UI currently shows event type ("AgentFinish") instead of agent identity ("Researcher"). Tracked for next step_callback-touching slice or v1.0b polish.
  - `trip-concierge-awf` (P2, Sunday morning): Wire real auth providers (AUTH_GOOGLE_ID + Resend) for dev environment OR document `web/scripts/mint-session-cookie.ts` as the official local-dev auth path.

- **Tickets closed in this slice:**
  - `trip-concierge-8yb`: Slice 4.5c application shell (closed at merge).
- **Merge:** _<placeholder — post-merge footer convention>_

### Slice 4.6: Edit and regenerate (block-level + day-level)

- [x] **Done when:** PRD §F5 partial-compliance shipped per Q1=(b) sign-off: Day regenerate + Block alternative (find + apply-via-refine) + Lock toggle (always-visible material icon, optimistic UI) work end to end on `/trips/[id]`. Locked blocks survive day regenerate via the existing slice-3.3 hard contract (Logistics Planner reads `Block.locked` at dispatch time). The new block-action cluster (`mt-3 flex justify-end gap-2`) hosts both block-scoped actions; v1.0b extends with Undo.
- ⚠️ **PRD §F5 partial compliance:** Undo last change is deferred to v1.0b under `trip-concierge-<new>` (P2). v1.0a release criteria include explicit §F5 review at Phase 5 closeout. The deferral was deliberate (Q1=b sign-off): a real Undo requires a trip-mutation history layer (lock toggle, swap, regenerate) — out of scope for the 4-commit budget. v1.0a ships 3-of-4 §F5 controls; partial compliance is honest.
- **4-commit decomposition:**
  - Commit 1 (`ec84ab9`) — Backend PATCH `/trips/{trip_id}/blocks/{block_id}` for lock toggle (metadata column write, no Redis touch, no enqueue, no 409 guard per Q5 design). 8 tests + live curl smoke.
  - Commit 2 (`307a0bd`) — Web Day regenerate UX: `regenerateDayAction` + `<RegenerateDayDialog />` (native `<dialog>` + showModal, optional hint, lock-preservation + ~3-5 min disclosure copy) + `<TripDay />` header restructured (`flex items-baseline justify-between`) with right-side trigger. 8 tests + browser smoke (4 Regenerate buttons on Coorg 4-day trip).
  - Commit 3 (`cdde680`) — Block alternative + apply-via-refine: `findAlternativeAction` (synchronous 90s wait, POST `/blocks/{id}/alternative`) + `applyAlternativeAction` (synthesizes `refinement_description` with optional Reason clause per Q-impl-c3-synth (b), POST `/trips/{id}/refine`) + `<BlockAlternativeDialog />` with 3-state machine + `<TripBlock />` action-cluster integration. 14 tests + browser smoke (30 "Swap this" buttons render on Coorg 4-day trip).
  - Commit 4 — Lock toggle UI + apply-confirm polish + spec amendment + docs: `setBlockLockAction` + `<BlockLockToggle />` (always-visible icon, optimistic UI with revert + 3s inline error badge per Q-impl-c4a fallback — no toast primitive scope creep) + 4-state dialog machine extension (idle → loading → showing → confirming, Back-to-options preserves alternatives per Q-impl-c4b=A, Confirm fires applyAlternativeAction) + spec §9.17 block-action cluster pattern + BUILD_PLAN entry.
- **Q4=A apply-via-refine architectural decision:** the chosen alternative is applied through `refine_trip` (hierarchical re-plan, ~10 min) rather than a direct Block write. Preserves the Budget Auditor invariant — sub-budget per day still checked — and keeps the apply path identical to every other user-driven trip mutation. Trade-off accepted: 10 min for a venue swap is heavy, but the alternative (skipping the auditor) breaks the budget guarantee.
- **Files created:**
  - `backend/app/routes/block_lock.py` + `backend/tests/test_block_lock_route.py`
  - `web/components/regenerate-day-dialog.tsx` + `web/tests/regenerate-day-dialog.test.tsx`
  - `web/components/block-alternative-dialog.tsx` + `web/tests/block-alternative-dialog.test.tsx`
  - `web/components/block-lock-toggle.tsx` + `web/tests/block-lock-toggle.test.tsx`
- **Files modified:** `web/lib/actions.ts` (3 new Server Actions), `web/components/trip-block.tsx` + `web/components/trip-day.tsx` (action-cluster integration), `web/app/trips/[id]/page.tsx` (thread tripId/userId), `backend/app/main.py` (router wire), `docs/design-spec.md` (§9.17 + v1.0.6 changelog), `BUILD_PLAN.md`.
- **Tests:** 38 net new (8 backend + 30 web vitest). Cumulative web vitest: 185.
- **Followup tickets filed during slice 4.6:**
  - `trip-concierge-wew` (P2): User-ownership-check sweep across all trip routes (deferred from commit 1 — inherits the existing MCP-token-presence-only pattern; v1.0b security review).
  - `trip-concierge-mbw` (P2): Undo support for block-level mutations (lock toggle, swap, regenerate) in v1.0b. Captures real user expectation across the cluster.
- **Beads:**
  - `trip-concierge-5qe`: Slice 4.6 (closed at merge).

### Post-slice-4.6 hotfix arc (2026-06-08): three P1s landed back-to-back after Phase 3 manual smoke

The slice-4.6 close-out led directly into a same-day hotfix arc. Phase 3 manual smoke of the Pondicherry trip surfaced three independent P1 regressions; each landed as its own merged PR with the same discipline (failing test → impl → per-commit smoke → PR → CI → merge → log archive → service restart if needed → bd close). Documented here because the arc reshaped one PRD §F8 design point + added one new spec section + amended discipline rules' application.

**`trip-concierge-nwk` — Dialog modal-mode regression (merge SHA `77c76e4`, PR #47)**
- All 3 dialogs (NewTripDialog from 4.5c, RegenerateDayDialog + BlockAlternativeDialog from 4.6) had declarative `<dialog open>` JSX that caused `showModal()` to throw `InvalidStateError` silently. Dialogs rendered non-modal — no top-layer, no Escape close, no ::backdrop; map markers + DayChipTimeline tooltips overlapped
- Fix: imperative-useEffect pattern (remove declarative `open`, drive showModal/close via useEffect, backdrop-click handler with target===currentTarget). Single-file refactor per dialog, identical shape
- New `web/vitest.setup.ts` polyfills `HTMLDialogElement.{showModal, close}` in jsdom with real-browser semantics (InvalidStateError on declarative open) so the regression test catches it via `spy.mock.results[0].type === "return"`
- Spec **§9.18 Dialog modal-mode pattern** added with wrong-shape/right-shape comparison + v1.0.7 changelog. Banked observation: workarounds for test infrastructure should also be tested at the level they bypass
- 9 net new vitest tests (3 per dialog: showModal-returns-cleanly + Escape close + backdrop click)

**`trip-concierge-kyh` Path B — task_callback agent_role enrichment (merge SHA `96bd251`, PR #48)**
- Original diagnostic hypothesis (worker drift) refuted by post-restart regenerate showing 0 step events on fresh worker code. Root cause corrected: **CrewAI 1.14.5's `step_callback` fires on ReAct intermediate steps; single-shot LLM outputs produce 0 step events** — Saturday-Coorg's 7 events were the OUTLIER, not the regression-shape
- Path B fix: surface `task_completed` events as primary visibility (previously filtered out as "redundant CrewAI hook"); enrich both AgentFinish + task_completed with `agent_role` extracted from CrewAI `step.agent.role` / `task_output.agent`
- Frontend: PlanHistoryPanel removes filter, adds `_TaskCompletedRow` with `check_circle` icon (vs psychology for AgentFinish), titles rows with `agent_role` (event-name fallback for legacy data), friendlier footer copy ("N reasoning steps · M agent completions"), sr-only event-type for screen readers
- Discharges `trip-concierge-nhm` (its explicit scope was the agent_role enrichment)
- Path A (ReAct-depth-independence v1.0b) filed as `trip-concierge-7n6` for v1.0b architectural sharpening
- Worker restart per discipline rule step 5b (uvicorn + worker both restarted; PIDs 33125 + 33126 at 19:32 IST)

**`trip-concierge-3x5` — GET /plan/status latest-JobRun semantic (merge SHA `feb21c9`, PR #49)**
- Discovered immediately after kyh Path B browser verification. PlanHistoryPanel on Coorg rendered "No agent activity recorded" because GET `/plan/status` returned the latest-by-time JobRun's `agent_summary` — and the latest was a 1-event sparse regen, displacing the rich 11-event original plan_trip
- Fix: `_latest_job_run` SQL changed to `ORDER BY jsonb_array_length(agent_summary) DESC NULLS LAST, created_at DESC`. Richness-first; latest-time tiebreaker. Single helper, two call sites, ordering-semantic-neutral for the POST guard
- v1.0b architectural sharpening (kind-aware JobRun selection — "original plan vs refines vs regens") tracked as `trip-concierge-d42`
- Uvicorn-only restart (worker untouched). 2 new pytest tests pin richness-bias + tiebreaker

**Cumulative tests after the arc**: backend 223/223, web vitest 200/200. Cumulative session deferrals: 7 tickets filed (`nwk` + `kyh` + `3x5` closed; `7n6` + `d42` + `mbw` + `wew` + `aqx` + `82y` open; `nhm` discharged). Three banked observations captured in respective ticket bodies — test-passes-but-production-breaks footgun; investigation-from-symptoms; outlier-vs-regression-distinction; frontend-filters-can-mask-backend-regressions; diagnostic-hypothesis-can-be-wrong-but-discipline-is-right.

### Slice 4.7: Source citations expansion + "why this was picked"

- [ ] **Done when:** Tapping a block expands to show source list, confidence indicator, and rationale.
- **Files to create:** `web/components/BlockDetail.tsx`, `web/components/ConfidenceBadge.tsx`
- **Tests:** expand/collapse interaction test.

### Slice 4.8: Visible agent activity panel

- [ ] **Done when:** Collapsible "How this plan was made" panel at the top of each day shows the agent activity from the `JobRun.agent_summary` JSONB column (one row per planning job, per-agent events captured via CrewAI step_callback).
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
