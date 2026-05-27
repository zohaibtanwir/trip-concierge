# CLAUDE.md

This file is the entry point for any Claude Code session in this repo. Read it first, every session.

---

## What this project is

**Trip Concierge** — a multi-agent AI travel planner with two surfaces:
1. An **MCP server** that lives inside Claude Desktop / ChatGPT
2. A **responsive PWA** at `tripconcierge.app`

One backend powers both. The agents are built with **CrewAI**. The whole point of this project is to learn CrewAI deeply (sequential vs hierarchical process, agent-to-agent delegation, built-in memory) while shipping a credible product.

Full product spec: `docs/prd.md`
Build plan and slices: `BUILD_PLAN.md`
Agent definitions: `agents/prompts.md`

---

## Tech stack (pinned, not negotiable)

| Layer | Choice |
|---|---|
| Agent orchestration | CrewAI (latest stable, pinned exactly) |
| Primary LLM | Claude Sonnet 4 via Anthropic SDK |
| API service | FastAPI + uvicorn |
| MCP server | Python `mcp` SDK |
| Web frontend | Next.js 15 App Router + Tailwind |
| Maps | MapLibre GL + OSM tiles |
| Database | PostgreSQL 16 |
| Vector store | pgvector extension |
| Cache / queue | Redis |
| Auth | Auth.js (NextAuth) — email magic link + Google OAuth |
| Search tools | Tavily, Serper |
| Observability | Langfuse |
| Package manager (Python) | uv |
| Package manager (Node) | pnpm |
| Test runner (Python) | pytest |
| Test runner (Node) | vitest |
| Linter (Python) | ruff |
| Linter (Node) | biome |
| Type checker (Python) | mypy strict mode |
| Type checker (Node) | tsc strict |

**Do not introduce a new dependency without updating this list and `BUILD_PLAN.md`.**

---

## Hard rules — never violate

These exist because of the supply chain attack landscape in 2026 (Axios, TanStack, Mistral, Laravel, node-ipc, Bitwarden CLI all compromised in the last 8 weeks).

1. **No `axios`. Ever.** Use native `fetch` or `ky`. CI will fail the build if `axios` appears anywhere in the lockfile.
2. **No ranged dependencies.** Every `package.json` and `pyproject.toml` entry uses exact versions. No `^`, no `~`, no `>=`. If you need to upgrade, do it as a deliberate PR.
3. **`pnpm install --ignore-scripts` by default.** Allowlist for build tools only. Add the package to `.npmrc` allowlist explicitly.
4. **No `pull_request_target` workflows in GitHub Actions.** This is how TanStack got compromised.
5. **Pin GitHub Actions to full SHA**, not tags. `uses: actions/checkout@v4` is wrong. `uses: actions/checkout@<full-sha>` is right.
6. **Denylist packages** (never reintroduce within 60 days of compromise disclosure):
   - `axios`, `node-ipc`, `mistralai`, `guardrails-ai`
   - All `@tanstack/*` packages (use Next.js App Router defaults instead)
   - `@uipath/*`, `@squawk/*`, `intercom-client`, `opensearch-project/opensearch`
7. **Anthropic SDK pinned exactly.** No experimental AI tooling SDKs.
8. **Lockfiles are sacred.** Any PR that changes the lockfile gets a second-pair-of-eyes review before merge.

---

## Always do

- **Test first.** For every new feature or bug fix, write a failing test before the implementation. The test goes in `tests/` mirroring the source path.
- **Run the test suite before declaring a slice done.** `make test` runs both Python and Node tests.
- **Run linters and type checkers before committing.** `make check` runs `ruff`, `mypy`, `biome`, `tsc`.
- **Update `BUILD_PLAN.md`** when a slice is completed. Mark it `[x]` and link to the merge commit.
- **Use Beads for task tracking.** `bd ready` to see what's unblocked. `bd update <id> --claim` when starting (atomic: sets in_progress + assignee). `bd close <id>` when complete. Issue IDs look like `trip-concierge-a3f2dd`.
- **Write structured logs**, never print statements. Python: `structlog`. TypeScript: `pino`.
- **Use type hints everywhere in Python.** Mypy strict mode is on; the build fails if you skip them.
- **Prefer composition over inheritance**, prefer functions over classes when stateless.
- **Read `agents/prompts.md` before touching any CrewAI agent code.** The prompts are version-controlled and changes need rationale in the commit message.

## Never do

- **Never use `npm install` or `pip install` ad hoc.** Always go through the lockfile (`pnpm add`, `uv add`).
- **Never commit a `.env` file.** Only `.env.example` is committed.
- **Never log API keys, tokens, user emails, or trip contents.** Use structured logging with redaction rules.
- **Never hardcode a URL, secret, or feature flag.** Read from `config.py` (Python) or `env.ts` (TypeScript).
- **Never write a bare `except:` in Python.** Catch specific exceptions; let unknown errors bubble.
- **Never use `any` in TypeScript.** If you genuinely need it, comment why; reviewer will push back.
- **Never call the LLM provider directly from a route handler.** All LLM calls go through the agent layer.
- **Never modify a CrewAI agent's `role`/`goal`/`backstory` without updating `agents/prompts.md`.**
- **Never claim a feature is done without a passing test and a passing lint/typecheck run.**

---

## Directory structure

```
trip-concierge/
├── CLAUDE.md                  # this file
├── BUILD_PLAN.md              # vertical slices, in order
├── Makefile                   # entry-point commands
├── pyproject.toml             # uv workspace root (members: backend, agents, mcp_server)
├── docker-compose.yml         # postgres (pgvector), redis
├── docs/
│   └── prd.md                 # full product spec
├── agents/                    # workspace member — Agents Service (FastAPI + arq worker)
│   ├── pyproject.toml
│   ├── prompts.md             # CrewAI agent definitions + MCP tool descriptions
│   ├── researcher.py
│   ├── local_expert.py
│   ├── logistics.py
│   ├── budget_auditor.py
│   ├── crew.py                # crew composition + Python-orchestrated audit loop
│   ├── service.py             # FastAPI app: POST /run (used by backend via HTTP)
│   ├── schemas.py             # AuditedPlan / TripPlan / Day / Block — shared via workspace
│   └── tools/
├── backend/                   # workspace member — Backend API (FastAPI)
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py            # FastAPI entry
│   │   ├── config.py
│   │   ├── routes/
│   │   ├── models/            # SQLAlchemy models (Trip, Day, Block, Source, AgentRun, User)
│   │   ├── schemas/           # Pydantic schemas (HTTP layer)
│   │   ├── services/
│   │   └── db/
│   │       └── migrations/    # Alembic
│   └── tests/
├── mcp_server/                # workspace member — MCP stdio + HTTP server
│   ├── pyproject.toml
│   ├── server.py
│   ├── tools/                 # one module per MCP tool
│   └── tests/
├── web/                       # NOT a uv workspace member (Node/pnpm project)
│   ├── package.json
│   └── ...
├── .claude/
│   └── rules/                 # one file per recurring rule
├── .beads/                    # Beads (Dolt embedded) — local-only via stealth mode
│   └── embeddeddolt/          # excluded by .git/info/exclude; seed via scripts/seed_beads.sh
└── .github/
    └── workflows/             # CI — pinned to SHA, no pull_request_target
```

**Why `agents` is both a workspace member AND a separate service:** the workspace is a dev-time convenience (shared Pydantic types, single `uv sync`, type-checking sees across projects). The service split is a runtime requirement — the 4-agent crew takes ~9 minutes per kickoff and would time out any HTTP gateway if it ran in the backend's request thread. The two layers solve different problems; see PRD §2.1 and the Slice 2.5a / 2.5b / 2.5c spec in BUILD_PLAN.md.

**Two parallel workspace systems.** Python uses uv workspace at the repo root (root `pyproject.toml` lists members: `backend`, `agents`; `mcp_server` joins in slice 3.1). Node uses pnpm inside `web/` standalone. They don't know about each other — there's no top-level "monorepo tool" wrapping both.

---

## Commands

| Command | What it does |
|---|---|
| `make setup` | Install all dependencies (uv + pnpm), set up pre-commit hooks, initialize DB |
| `make dev` | Run backend (FastAPI), MCP server, and web frontend concurrently |
| `make test` | Run all tests (pytest + vitest) |
| `make check` | Run linters and type checkers |
| `make db.migrate` | Apply Alembic migrations |
| `make db.reset` | Drop and recreate the local DB (destructive — confirms) |
| `make mcp.test` | Test MCP server against Claude Desktop config |
| `bd ready` | Show all unblocked Beads tickets (top of list is what to grab next) |
| `bd update <id> --claim` | Claim a ticket (atomic: status=in_progress, assignee=you) |
| `bd close <id>` | Mark a Beads ticket as done |
| `bash scripts/seed_beads.sh` | Re-seed all 33 BUILD_PLAN.md slices on a fresh clone |

---

## Environment variables

Defined in `.env.example`. Copy to `.env.local` (web) and `.env` (backend) before first run.

| Var | Where | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | backend, mcp_server | LLM calls |
| `DATABASE_URL` | backend | Postgres connection |
| `REDIS_URL` | backend | Cache + queue |
| `TAVILY_API_KEY` | backend | Researcher agent search |
| `SERPER_API_KEY` | backend | Researcher agent fallback |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | backend, mcp_server | Tracing |
| `NEXTAUTH_SECRET` | web | Auth signing |
| `NEXTAUTH_URL` | web | Auth callbacks |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | web | OAuth |
| `BACKEND_URL` | web | Internal API base URL |
| `TC_MCP_TOKEN_SECRET` | backend, mcp_server | MCP token signing |
| `RESEND_API_KEY` | web | Magic link emails |

---

## How to work on this repo

**Session start checklist:**
1. `git pull`
2. `bd ready` — see what's unblocked; grab the top one
3. `bd update <id> --claim` to mark it in_progress
4. Read the ticket; if it references a slice in `BUILD_PLAN.md`, read that slice
5. If the ticket touches agents, read `agents/prompts.md`
6. Write the failing test first
7. Implement
8. `make check && make test`
9. Commit with a message that references the Beads ID and the slice (format: `feat(slice-X.Y): <change>` with `Refs: trip-concierge-<hash>` in the body)
10. `bd close <id>` and push

**If you're blocked:**
- Don't invent. Read the relevant doc.
- If the doc is wrong or missing something, update it in the same PR.
- If the rule in this file is wrong, propose a change in a separate PR — never silently violate it.

**If you're tempted to add a dependency:**
- Search for it on Socket.dev first. Check publish history, maintainer count, recent activity.
- Add it to the tech stack table above and to `BUILD_PLAN.md` rationale.
- Pin exact version. Add to `.npmrc` allowlist if it needs install scripts (it probably shouldn't).

---

## When in doubt

- Ship the smallest thing that proves the slice works.
- Add tests, then expand functionality, then add observability.
- If a slice is taking more than 3 sessions, decompose it further in `BUILD_PLAN.md`.
- Never silently broaden scope. Open a new ticket instead.

---

_Last updated: 2026-05-24_
