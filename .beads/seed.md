# Beads Seed

Run this once at the start of the project to populate Beads with the initial set of tickets in dependency order. After this, `bd next` returns the right ticket on every session.

## Usage

```bash
# From repo root, after Beads is installed and initialized:
bash scripts/seed_beads.sh
```

Or run the `bd` commands below manually.

---

## Tickets — Phase 0 (Foundations)

```bash
# 0.1 Repo skeleton
bd create \
  --title "Slice 0.1: Repo skeleton" \
  --body "See BUILD_PLAN.md Slice 0.1. Set up Makefile, FastAPI /health, empty Next.js page, empty MCP server, .env.example, .gitignore." \
  --tags "phase-0,setup" \
  --priority high

# 0.2 CI pipeline
bd create \
  --title "Slice 0.2: CI pipeline" \
  --body "See BUILD_PLAN.md Slice 0.2. GitHub Actions CI running make check && make test. Pinned to full SHAs. No pull_request_target." \
  --tags "phase-0,setup,security" \
  --depends-on "slice-0.1" \
  --priority high

# 0.3 Pre-commit hooks + Beads init
bd create \
  --title "Slice 0.3: Pre-commit hooks and Beads init" \
  --body "See BUILD_PLAN.md Slice 0.3. .pre-commit-config.yaml runs ruff and biome. Beads seeded from this file." \
  --tags "phase-0,setup" \
  --depends-on "slice-0.2" \
  --priority high
```

## Tickets — Phase 1 (Data model + first agent)

```bash
# 1.1 Postgres + Alembic
bd create \
  --title "Slice 1.1: Postgres + Alembic setup" \
  --body "See BUILD_PLAN.md Slice 1.1. users and trips tables. Alembic migrations. make db.migrate works." \
  --tags "phase-1,backend,db" \
  --depends-on "slice-0.3" \
  --priority high

# 1.2 Trip CRUD endpoints
bd create \
  --title "Slice 1.2: Trip CRUD endpoints" \
  --body "See BUILD_PLAN.md Slice 1.2. POST /trips, GET /trips/{id}. Pydantic validation. Tests for happy path and 422." \
  --tags "phase-1,backend,api" \
  --depends-on "slice-1.1" \
  --priority high

# 1.3 First CrewAI agent (Researcher, stubbed)
bd create \
  --title "Slice 1.3: Researcher agent (stubbed)" \
  --body "See BUILD_PLAN.md Slice 1.3 and agents/prompts.md §1.1. CrewAI Agent for Researcher. Returns fixture data. No LLM call yet." \
  --tags "phase-1,agents" \
  --depends-on "slice-1.2" \
  --priority high

# 1.4 Wire LLM into Researcher
bd create \
  --title "Slice 1.4: Researcher with live LLM" \
  --body "See BUILD_PLAN.md Slice 1.4. Real Anthropic SDK call. Tavily web search tool wired. Langfuse trace appears." \
  --tags "phase-1,agents,llm" \
  --depends-on "slice-1.3" \
  --priority high
```

## Tickets — Phase 2 (Full crew, sequential)

```bash
# 2.1 Local Expert agent
bd create \
  --title "Slice 2.1: Local Expert agent" \
  --body "See BUILD_PLAN.md Slice 2.1 and agents/prompts.md §1.2." \
  --tags "phase-2,agents" \
  --depends-on "slice-1.4" \
  --priority high

# 2.2 Logistics Planner agent
bd create \
  --title "Slice 2.2: Logistics Planner agent" \
  --body "See BUILD_PLAN.md Slice 2.2 and agents/prompts.md §1.3." \
  --tags "phase-2,agents" \
  --depends-on "slice-2.1" \
  --priority high

# 2.3 Budget Auditor agent
bd create \
  --title "Slice 2.3: Budget Auditor agent" \
  --body "See BUILD_PLAN.md Slice 2.3 and agents/prompts.md §1.4. Two-retry policy enforced." \
  --tags "phase-2,agents" \
  --depends-on "slice-2.2" \
  --priority high

# 2.4 Day/Block/Source models
bd create \
  --title "Slice 2.4: Day, Block, Source models" \
  --body "See BUILD_PLAN.md Slice 2.4. SQLAlchemy models + Alembic migration. Crew output persisted." \
  --tags "phase-2,backend,db" \
  --depends-on "slice-2.3" \
  --priority high

# 2.5 /trips/{id}/plan endpoint
bd create \
  --title "Slice 2.5: Full sequential plan endpoint" \
  --body "See BUILD_PLAN.md Slice 2.5. End-to-end generation via 4-agent sequential crew. Persistence wired." \
  --tags "phase-2,backend,agents" \
  --depends-on "slice-2.4" \
  --priority high
```

## Tickets — Phase 3 (MCP server)

```bash
# 3.1 MCP server skeleton + auth
bd create \
  --title "Slice 3.1: MCP server skeleton with magic-link auth" \
  --body "See BUILD_PLAN.md Slice 3.1. Claude Desktop connects, magic-link issues token, subsequent calls authenticated." \
  --tags "phase-3,mcp,auth" \
  --depends-on "slice-2.5" \
  --priority high

# 3.2 create_trip tool
bd create \
  --title "Slice 3.2: create_trip MCP tool" \
  --body "See BUILD_PLAN.md Slice 3.2 and agents/prompts.md §4.1." \
  --tags "phase-3,mcp" \
  --depends-on "slice-3.1" \
  --priority high

# 3.3 get/refine/regenerate
bd create \
  --title "Slice 3.3: get_trip, refine_trip, regenerate_day tools" \
  --body "See BUILD_PLAN.md Slice 3.3 and agents/prompts.md §4.2-4.4. refine_trip uses Process.hierarchical." \
  --tags "phase-3,mcp" \
  --depends-on "slice-3.2" \
  --priority high

# 3.4 constraint/source/alternative/explain
bd create \
  --title "Slice 3.4: add_constraint, add_source, find_alternative, explain_recommendation tools" \
  --body "See BUILD_PLAN.md Slice 3.4 and agents/prompts.md §4.5-4.8. add_source ingests URL, embeds with pgvector." \
  --tags "phase-3,mcp" \
  --depends-on "slice-3.3" \
  --priority high

# 3.5 share/export
bd create \
  --title "Slice 3.5: share_trip and export_trip tools" \
  --body "See BUILD_PLAN.md Slice 3.5 and agents/prompts.md §4.10-4.11. PDF generation." \
  --tags "phase-3,mcp" \
  --depends-on "slice-3.4" \
  --priority medium
```

## Tickets — Phase 4 (Web app)

```bash
# 4.1 Auth.js
bd create \
  --title "Slice 4.1: Auth.js setup" \
  --body "See BUILD_PLAN.md Slice 4.1. Magic link + Google OAuth." \
  --tags "phase-4,web,auth" \
  --depends-on "slice-3.5" \
  --priority high

# 4.2 Trip list and detail pages
bd create \
  --title "Slice 4.2: Trip list and detail pages" \
  --body "See BUILD_PLAN.md Slice 4.2. Server components, fetch from backend API." \
  --tags "phase-4,web" \
  --depends-on "slice-4.1" \
  --priority high

# 4.3 Day card mobile-first
bd create \
  --title "Slice 4.3: Day card UI, mobile-first" \
  --body "See BUILD_PLAN.md Slice 4.3. 360px viewport, 44px touch targets, sticky day chip nav, swipe gestures." \
  --tags "phase-4,web,mobile" \
  --depends-on "slice-4.2" \
  --priority high

# 4.4 MapLibre
bd create \
  --title "Slice 4.4: Map view with MapLibre" \
  --body "See BUILD_PLAN.md Slice 4.4. Pins, route lines, tap-to-scroll-itinerary, two-column above 768px." \
  --tags "phase-4,web" \
  --depends-on "slice-4.3" \
  --priority high

# 4.5 Constraints + pace slider
bd create \
  --title "Slice 4.5: Constraint controls and pace slider" \
  --body "See BUILD_PLAN.md Slice 4.5. Bottom-sheet UI. Changes trigger plan regen." \
  --tags "phase-4,web" \
  --depends-on "slice-4.4" \
  --priority high

# 4.6 Edit and regenerate
bd create \
  --title "Slice 4.6: Block/day regenerate with lock preservation" \
  --body "See BUILD_PLAN.md Slice 4.6. Undo last change. Locked blocks preserved." \
  --tags "phase-4,web" \
  --depends-on "slice-4.5" \
  --priority high

# 4.7 Source citations + why this
bd create \
  --title "Slice 4.7: Source citations and why-this-not-that UI" \
  --body "See BUILD_PLAN.md Slice 4.7. Expand block to show sources, confidence, rationale." \
  --tags "phase-4,web,trust" \
  --depends-on "slice-4.6" \
  --priority high

# 4.8 Visible agent activity
bd create \
  --title "Slice 4.8: Agent activity panel" \
  --body "See BUILD_PLAN.md Slice 4.8. Collapsible top-of-day panel showing AgentRun records." \
  --tags "phase-4,web,trust" \
  --depends-on "slice-4.7" \
  --priority medium

# 4.9 Share/export UI
bd create \
  --title "Slice 4.9: Share menu and export buttons" \
  --body "See BUILD_PLAN.md Slice 4.9. Share link, PDF download, WhatsApp share, Google Maps export." \
  --tags "phase-4,web" \
  --depends-on "slice-4.8" \
  --priority medium

# 4.10 PWA / offline
bd create \
  --title "Slice 4.10: PWA manifest, service worker, offline mode" \
  --body "See BUILD_PLAN.md Slice 4.10. Installable. Offline cache. Lighthouse mobile ≥ 85." \
  --tags "phase-4,web,mobile" \
  --depends-on "slice-4.9" \
  --priority high
```

## Tickets — Phase 5 (Polish + deploy)

```bash
# 5.1 Hierarchical process
bd create \
  --title "Slice 5.1: Hierarchical process for refinement" \
  --body "See BUILD_PLAN.md Slice 5.1. refine_trip and complex edits use Process.hierarchical with manager LLM." \
  --tags "phase-5,agents" \
  --depends-on "slice-4.10" \
  --priority high

# 5.2 BYO research polish
bd create \
  --title "Slice 5.2: BYO research polish" \
  --body "See BUILD_PLAN.md Slice 5.2. Reddit threads, YouTube URLs, Google Maps lists all work." \
  --tags "phase-5,agents,ingestion" \
  --depends-on "slice-5.1" \
  --priority medium

# 5.3 Memory
bd create \
  --title "Slice 5.3: CrewAI memory enabled and surfaced in UI" \
  --body "See BUILD_PLAN.md Slice 5.3. Memory page shows what's remembered, allows delete." \
  --tags "phase-5,agents,memory" \
  --depends-on "slice-5.2" \
  --priority medium

# 5.4 Rate limit + cost dashboard
bd create \
  --title "Slice 5.4: Rate limiting and cost dashboard" \
  --body "See BUILD_PLAN.md Slice 5.4. Per-user limits. Internal /admin/costs page." \
  --tags "phase-5,backend,ops" \
  --depends-on "slice-5.3" \
  --priority high

# 5.5 Production deploy
bd create \
  --title "Slice 5.5: Production deploy" \
  --body "See BUILD_PLAN.md Slice 5.5. Backend on Fly.io/Hetzner. Web on Vercel. Postgres + Redis managed." \
  --tags "phase-5,ops,deploy" \
  --depends-on "slice-5.4" \
  --priority high

# 5.6 v1.0 release checklist
bd create \
  --title "Slice 5.6: v1.0 release checklist" \
  --body "See BUILD_PLAN.md Slice 5.6. Run through every checklist item before marking v1.0 done." \
  --tags "phase-5,release" \
  --depends-on "slice-5.5" \
  --priority high
```

---

## Notes on using Beads with Claude Code

- Run `bd next` at the start of each session to see what's ready.
- Beads automatically promotes tickets to "ready" when all their dependencies are done.
- If you finish a slice ahead of schedule and the next one isn't ready (e.g., it has multiple dependencies), check `bd list --ready` for parallel options.
- If a slice grows beyond 3 sessions, split it: `bd split <id>` and update `BUILD_PLAN.md` in the same PR.
- Tag tickets you're actively working on with `bd start <id>` so the dependency graph reflects in-flight work.
