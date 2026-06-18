# Trip Concierge

A multi-agent AI travel planner built around one principle: **planning a trip is conversational; consuming a trip is visual.** Each surface plays to its strength.

Trip Concierge has two front doors backed by one service:

1. An **MCP server** that lives inside Claude Desktop / ChatGPT — plan conversationally, in the chat you already use.
2. A **responsive PWA** at `tripconcierge.app` — view, refine, and consume trips on a map and timeline.

Under both is a **CrewAI** crew of four specialized agents that produce constraint-aware, source-cited, day-by-day itineraries.

> This project is also a deliberate learning artifact for CrewAI patterns — sequential vs. hierarchical process, agent-to-agent delegation, and built-in per-user memory.

---

## What makes it different

The 2026 AI-travel market is full of itinerary generators that produce a list and stop. Trip Concierge takes a point of view on what they miss:

- **Source-cited recommendations** — every venue carries a citation, not a hallucinated suggestion.
- **Hard constraints, not soft hints** — budget caps, mobility, dietary needs, and pace are *enforced* by a Budget Auditor agent, not politely suggested.
- **Mid-trip replanning** — when reality breaks the plan (delays, closures, fatigue), `replan_from_here` reflows the rest of the trip.
- **Bring-your-own research** — paste a Reddit thread, a YouTube vlog, or a friend's tips and the crew plans *with* your research, not in a vacuum.

---

## Architecture

```
        Claude / ChatGPT              Browser / Mobile
        (user's AI chat)             (tripconcierge.app)
               │                              │
        ┌──────▼───────┐              ┌───────▼───────┐
        │  MCP Server  │              │ PWA (Next.js) │
        │ (Python,     │              │               │
        │  stdio+HTTP) │              │               │
        └──────┬───────┘              └───────┬───────┘
               └──────────────┬───────────────┘
                              │
                      ┌───────▼────────┐
                      │  Backend API   │   202 Accepted in <1s,
                      │   (FastAPI)    │   then enqueue
                      └───┬────────┬───┘
              enqueue ────┘        └──── reads/writes
                          │        │
                   ┌──────▼────────▼──────┐
                   │  Postgres + pgvector │
                   │ trips · days · blocks│
                   │ sources · job_runs   │
                   └──────────┬───────────┘
                              ▲ persists results
                   ┌──────────┴────────────────┐
                   │  Agents Service           │
                   │  (FastAPI + arq worker)   │
                   │   CrewAI 4-agent crew:    │
                   │    Researcher             │
                   │    Local Expert           │
                   │    Logistics              │
                   │    Budget Auditor         │
                   └──────────┬────────────────┘
                              │ jobs in/out
                       ┌──────▼──────┐
                       │    Redis    │  (arq queue + cache)
                       └─────────────┘

External calls (from the Agents Service):
  Anthropic Claude Sonnet 4 (LLM) · Tavily / Serper (search) · Langfuse (tracing)
```

**Why the Agents Service is split out.** The 4-agent crew takes ~9 minutes per kickoff. Production HTTP gateways cap requests at ~60s, so running the crew inside the request thread would time out. Instead, the user-facing API returns `202 Accepted` in under a second with a `job_id`; the crew runs in a background worker pool gated by Redis; the PWA and MCP poll for status. (Decided in the Slice 2.5 architecture review — see `docs/prd.md` §2.1.)

### The four agents

| Agent | Role |
|---|---|
| **Researcher** | Finds candidate destinations and venues via web search (Tavily/Serper), with source URLs. |
| **Local Expert** | Narrows candidates to the best fit and explains *why this, not that*. |
| **Logistics Planner** | Builds the day-by-day itinerary with ordered blocks and travel times. |
| **Budget Auditor** | Enforces the budget — applies its own cuts and drives a bounded revision loop. |

Agent prompts (`role` / `goal` / `backstory`) and MCP tool descriptions are version-controlled in `agents/prompts.md`, which is the canonical source.

---

## Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | CrewAI |
| Primary LLM | Claude Sonnet 4 (via Anthropic SDK) |
| API service | FastAPI + uvicorn |
| Background queue | arq worker on Redis |
| MCP server | Python `mcp` SDK (stdio + HTTP) |
| Web frontend | Next.js 15 (App Router) + Tailwind |
| Maps | MapLibre GL + OpenStreetMap tiles |
| Database | PostgreSQL 16 + pgvector |
| Cache / queue | Redis |
| Auth | Auth.js (NextAuth) — email magic link + Google OAuth |
| Search tools | Tavily, Serper |
| Observability | Langfuse |
| Package managers | `uv` (Python), `pnpm` (Node) |
| Tests | pytest (Python), vitest (Node), Playwright (e2e) |
| Lint / types | ruff + mypy (strict) · biome + tsc (strict) |

---

## Repository layout

```
trip-concierge/
├── CLAUDE.md          # entry-point doc for any Claude Code session — read first
├── BUILD_PLAN.md      # vertical slices, in build order
├── Makefile           # entry-point commands
├── docker-compose.yml # postgres (pgvector) + redis
├── docs/prd.md        # full product spec
├── agents/            # Agents Service (FastAPI + arq worker) — CrewAI crew
│   └── prompts.md     # canonical agent + MCP tool definitions
├── backend/           # Backend API (FastAPI) + arq worker + Alembic migrations
├── mcp_server/        # MCP stdio + HTTP server (talks to backend over HTTP)
├── web/               # Next.js PWA (pnpm; not a uv workspace member)
└── .github/workflows/ # CI — Actions pinned to full SHA, no pull_request_target
```

Python projects (`backend`, `agents`, `mcp_server`) form a single **uv workspace** rooted at the repo. The `web/` app is a standalone **pnpm** project. There is no top-level monorepo tool wrapping both.

---

## Getting started

### Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package manager)
- [`pnpm`](https://pnpm.io/) (Node package manager)
- Docker (for Postgres + Redis via `docker-compose.yml`)

### Setup

```bash
# 1. Install all dependencies (uv + pnpm) and pre-commit hooks
make setup

# 2. Configure environment
cp .env.example .env          # backend / agents / mcp_server
cp .env.example web/.env.local # web
# fill in ANTHROPIC_API_KEY, TAVILY_API_KEY, etc.

# 3. Bring up Postgres + Redis, then migrate
make services.up
make db.migrate
```

See **Environment variables** in `CLAUDE.md` for the full list of required keys.

### Running

```bash
make agents.dev      # Agents Service (FastAPI)  — port 8001
make backend.worker  # arq worker draining crew jobs from Redis
# backend uvicorn + web pnpm dev are wired into `make dev` (in progress)
```

To connect the MCP server to Claude Desktop, see `mcp_server/README.md`.

---

## Common commands

| Command | What it does |
|---|---|
| `make setup` | Install all deps, hooks, initialize DB |
| `make test` | Run all tests (pytest + vitest) |
| `make check` | Run linters + type checkers (ruff, mypy, biome, tsc) |
| `make db.migrate` | Apply Alembic migrations |
| `make db.reset` | Drop and recreate the local DB (destructive — confirms) |
| `make services.up` | Start Postgres + Redis |
| `bd ready` | Show unblocked task-tracker tickets (Beads) |

---

## How this project is built

Work proceeds in **vertical slices** tracked in `BUILD_PLAN.md`, each sized for 1–3 sessions and tracked as a [Beads](https://github.com/steveyegge/beads) ticket. Current status: **Phases 0–3 complete** (foundations, data model, full crew, MCP server); **Phase 4 (web app) in progress**; Phase 5 (polish + deploy) remaining.

Conventions enforced across the repo (see `.claude/rules/`):

- **Test first.** A failing test precedes every feature or fix.
- **Pin every dependency exactly** — no ranges. Lockfiles are reviewed. A hard denylist (`axios`, compromised `@tanstack/*`, etc.) is enforced in CI, born of the 2026 supply-chain attack wave.
- **Architectural checkpoints** — propose the file tree before writing code that crosses project boundaries.
- **`make check && make test` green** before any slice is called done.

`CLAUDE.md` is the canonical contributor guide — start there.

---

## Status & non-goals

This is a v1.0 build in active development. Out of scope for v1.0: in-app booking/payments (hand-off to Booking.com, Skyscanner, etc.), native mobile apps (the PWA covers MVP), user-generated content/social, and flight/hotel search engines.
