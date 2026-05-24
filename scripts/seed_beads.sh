#!/usr/bin/env bash
# Seed Beads with the 33 BUILD_PLAN.md slices in dependency order.
# Translates .beads/seed.md to bd 0.49 flags:
#   --body      -> --description
#   --tags      -> --labels
#   --priority high/medium -> 1 / 2  (0=highest, 4=lowest)
#   --depends-on -> bd dep add <new> <previous>  (post-create)
set -euo pipefail

mk() {
  # mk "<title>" "<description>" "<labels>" <priority>
  bd create --silent --title "$1" -d "$2" -l "$3" -p "$4"
}

# --- Phase 0 ---
S01=$(mk "Slice 0.1: Repo skeleton" \
  "See BUILD_PLAN.md Slice 0.1. Set up Makefile, FastAPI /health, empty Next.js page, empty MCP server, .env.example, .gitignore." \
  "phase-0,setup" 1)

S02=$(mk "Slice 0.2: CI pipeline" \
  "See BUILD_PLAN.md Slice 0.2. GitHub Actions CI running make check && make test. Pinned to full SHAs. No pull_request_target." \
  "phase-0,setup,security" 1)
bd dep add "$S02" "$S01"

S03=$(mk "Slice 0.3: Pre-commit hooks and Beads init" \
  "See BUILD_PLAN.md Slice 0.3. .pre-commit-config.yaml runs ruff and biome. Beads seeded from this file." \
  "phase-0,setup" 1)
bd dep add "$S03" "$S02"

# --- Phase 1 ---
S11=$(mk "Slice 1.1: Postgres + Alembic setup" \
  "See BUILD_PLAN.md Slice 1.1. users and trips tables. Alembic migrations. make db.migrate works." \
  "phase-1,backend,db" 1)
bd dep add "$S11" "$S03"

S12=$(mk "Slice 1.2: Trip CRUD endpoints" \
  "See BUILD_PLAN.md Slice 1.2. POST /trips, GET /trips/{id}. Pydantic validation. Tests for happy path and 422." \
  "phase-1,backend,api" 1)
bd dep add "$S12" "$S11"

S13=$(mk "Slice 1.3: Researcher agent (stubbed)" \
  "See BUILD_PLAN.md Slice 1.3 and agents/prompts.md §1.1. CrewAI Agent for Researcher. Returns fixture data. No LLM call yet." \
  "phase-1,agents" 1)
bd dep add "$S13" "$S12"

S14=$(mk "Slice 1.4: Researcher with live LLM" \
  "See BUILD_PLAN.md Slice 1.4. Real Anthropic SDK call. Tavily web search tool wired. Langfuse trace appears." \
  "phase-1,agents,llm" 1)
bd dep add "$S14" "$S13"

# --- Phase 2 ---
S21=$(mk "Slice 2.1: Local Expert agent" \
  "See BUILD_PLAN.md Slice 2.1 and agents/prompts.md §1.2." \
  "phase-2,agents" 1)
bd dep add "$S21" "$S14"

S22=$(mk "Slice 2.2: Logistics Planner agent" \
  "See BUILD_PLAN.md Slice 2.2 and agents/prompts.md §1.3." \
  "phase-2,agents" 1)
bd dep add "$S22" "$S21"

S23=$(mk "Slice 2.3: Budget Auditor agent" \
  "See BUILD_PLAN.md Slice 2.3 and agents/prompts.md §1.4. Two-retry policy enforced." \
  "phase-2,agents" 1)
bd dep add "$S23" "$S22"

S24=$(mk "Slice 2.4: Day, Block, Source models" \
  "See BUILD_PLAN.md Slice 2.4. SQLAlchemy models + Alembic migration. Crew output persisted." \
  "phase-2,backend,db" 1)
bd dep add "$S24" "$S23"

S25=$(mk "Slice 2.5: Full sequential plan endpoint" \
  "See BUILD_PLAN.md Slice 2.5. End-to-end generation via 4-agent sequential crew. Persistence wired." \
  "phase-2,backend,agents" 1)
bd dep add "$S25" "$S24"

# --- Phase 3 ---
S31=$(mk "Slice 3.1: MCP server skeleton with magic-link auth" \
  "See BUILD_PLAN.md Slice 3.1. Claude Desktop connects, magic-link issues token, subsequent calls authenticated." \
  "phase-3,mcp,auth" 1)
bd dep add "$S31" "$S25"

S32=$(mk "Slice 3.2: create_trip MCP tool" \
  "See BUILD_PLAN.md Slice 3.2 and agents/prompts.md §4.1." \
  "phase-3,mcp" 1)
bd dep add "$S32" "$S31"

S33=$(mk "Slice 3.3: get_trip, refine_trip, regenerate_day tools" \
  "See BUILD_PLAN.md Slice 3.3 and agents/prompts.md §4.2-4.4. refine_trip uses Process.hierarchical." \
  "phase-3,mcp" 1)
bd dep add "$S33" "$S32"

S34=$(mk "Slice 3.4: add_constraint, add_source, find_alternative, explain_recommendation tools" \
  "See BUILD_PLAN.md Slice 3.4 and agents/prompts.md §4.5-4.8. add_source ingests URL, embeds with pgvector." \
  "phase-3,mcp" 1)
bd dep add "$S34" "$S33"

S35=$(mk "Slice 3.5: share_trip and export_trip tools" \
  "See BUILD_PLAN.md Slice 3.5 and agents/prompts.md §4.10-4.11. PDF generation." \
  "phase-3,mcp" 2)
bd dep add "$S35" "$S34"

# --- Phase 4 ---
S41=$(mk "Slice 4.1: Auth.js setup" \
  "See BUILD_PLAN.md Slice 4.1. Magic link + Google OAuth." \
  "phase-4,web,auth" 1)
bd dep add "$S41" "$S35"

S42=$(mk "Slice 4.2: Trip list and detail pages" \
  "See BUILD_PLAN.md Slice 4.2. Server components, fetch from backend API." \
  "phase-4,web" 1)
bd dep add "$S42" "$S41"

S43=$(mk "Slice 4.3: Day card UI, mobile-first" \
  "See BUILD_PLAN.md Slice 4.3. 360px viewport, 44px touch targets, sticky day chip nav, swipe gestures." \
  "phase-4,web,mobile" 1)
bd dep add "$S43" "$S42"

S44=$(mk "Slice 4.4: Map view with MapLibre" \
  "See BUILD_PLAN.md Slice 4.4. Pins, route lines, tap-to-scroll-itinerary, two-column above 768px." \
  "phase-4,web" 1)
bd dep add "$S44" "$S43"

S45=$(mk "Slice 4.5: Constraint controls and pace slider" \
  "See BUILD_PLAN.md Slice 4.5. Bottom-sheet UI. Changes trigger plan regen." \
  "phase-4,web" 1)
bd dep add "$S45" "$S44"

S46=$(mk "Slice 4.6: Block/day regenerate with lock preservation" \
  "See BUILD_PLAN.md Slice 4.6. Undo last change. Locked blocks preserved." \
  "phase-4,web" 1)
bd dep add "$S46" "$S45"

S47=$(mk "Slice 4.7: Source citations and why-this-not-that UI" \
  "See BUILD_PLAN.md Slice 4.7. Expand block to show sources, confidence, rationale." \
  "phase-4,web,trust" 1)
bd dep add "$S47" "$S46"

S48=$(mk "Slice 4.8: Agent activity panel" \
  "See BUILD_PLAN.md Slice 4.8. Collapsible top-of-day panel showing AgentRun records." \
  "phase-4,web,trust" 2)
bd dep add "$S48" "$S47"

S49=$(mk "Slice 4.9: Share menu and export buttons" \
  "See BUILD_PLAN.md Slice 4.9. Share link, PDF download, WhatsApp share, Google Maps export." \
  "phase-4,web" 2)
bd dep add "$S49" "$S48"

S410=$(mk "Slice 4.10: PWA manifest, service worker, offline mode" \
  "See BUILD_PLAN.md Slice 4.10. Installable. Offline cache. Lighthouse mobile >= 85." \
  "phase-4,web,mobile" 1)
bd dep add "$S410" "$S49"

# --- Phase 5 ---
S51=$(mk "Slice 5.1: Hierarchical process for refinement" \
  "See BUILD_PLAN.md Slice 5.1. refine_trip and complex edits use Process.hierarchical with manager LLM." \
  "phase-5,agents" 1)
bd dep add "$S51" "$S410"

S52=$(mk "Slice 5.2: BYO research polish" \
  "See BUILD_PLAN.md Slice 5.2. Reddit threads, YouTube URLs, Google Maps lists all work." \
  "phase-5,agents,ingestion" 2)
bd dep add "$S52" "$S51"

S53=$(mk "Slice 5.3: CrewAI memory enabled and surfaced in UI" \
  "See BUILD_PLAN.md Slice 5.3. Memory page shows what's remembered, allows delete." \
  "phase-5,agents,memory" 2)
bd dep add "$S53" "$S52"

S54=$(mk "Slice 5.4: Rate limiting and cost dashboard" \
  "See BUILD_PLAN.md Slice 5.4. Per-user limits. Internal /admin/costs page." \
  "phase-5,backend,ops" 1)
bd dep add "$S54" "$S53"

S55=$(mk "Slice 5.5: Production deploy" \
  "See BUILD_PLAN.md Slice 5.5. Backend on Fly.io/Hetzner. Web on Vercel. Postgres + Redis managed." \
  "phase-5,ops,deploy" 1)
bd dep add "$S55" "$S54"

S56=$(mk "Slice 5.6: v1.0 release checklist" \
  "See BUILD_PLAN.md Slice 5.6. Run through every checklist item before marking v1.0 done." \
  "phase-5,release" 1)
bd dep add "$S56" "$S55"

echo "Seeded $(bd list --json 2>/dev/null | grep -c '"id"' || echo "?") tickets."
