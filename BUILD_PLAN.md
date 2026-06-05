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
