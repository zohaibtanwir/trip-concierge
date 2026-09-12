---
name: run-app
description: Launch the full Trip Concierge stack locally — Docker (Postgres+Redis), backend API, agents service, arq worker, and the web PWA. Use whenever asked to "run the app", "start the app", "bring up the stack", or verify a change in the real running app. Covers the full backend stack, not just the frontend.
---

# Run the Trip Concierge app (full stack)

"Run the app" means **the whole stack**, not just the Next.js frontend. The frontend
alone renders marketing pages but every data action (`Plan a trip`, `/trips`, sign-in)
calls `BACKEND_URL` and will fail without the backend, agents service, worker, Postgres,
and Redis all up. `make dev` is a TODO stub — launch the pieces individually as below.

## ⚠️ Read this before touching any env file

The **real, working env file is `backend/.env`** (git-ignored, populated by hand with
`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, Langfuse keys). Both `backend/app/config.py` and
`agents/src/trip_agents/config.py` read from it via an absolute path — **not** the repo
root `.env`.

- **NEVER `cp .env.example .env` / `cp .env.example backend/.env` without checking first.**
  Run `ls -la backend/.env` — if it exists, leave it alone. Overwriting it wipes the keys.
- The repo-root `.env` is **not read by anything**. Don't create it; if one appears with
  empty values, it's noise — delete it.
- The web app needs `web/.env.local`. If it's missing, create it (see step 4). If it
  exists, leave it.

## Prerequisites already satisfied on this machine

`uv`, `pnpm`, Docker Desktop installed; `web/node_modules` present. If a fresh clone:
`make setup` first.

## Launch sequence (verified 2026-06-28)

### 1. Start Docker, then Postgres + Redis
```bash
open -a Docker                         # if the daemon isn't running
# wait until `docker info` succeeds (usually a few seconds), then:
make services.up                       # postgres :5432, redis :6379, waits for healthy
```

### 2. Apply migrations
```bash
make db.migrate                        # alembic upgrade head
# sanity: docker exec trip-concierge-postgres psql -U postgres -d trip_concierge -c "select version_num from alembic_version;"
```

### 3. Verify backend/.env exists with keys — do NOT recreate it
```bash
ls -la backend/.env                    # must exist; if missing, ask the user for keys, don't fabricate
```

### 4. Ensure web/.env.local exists (create ONLY if missing)
**Use the project's canonical local dev secrets — do NOT `openssl rand` here.** A random
`NEXTAUTH_SECRET` breaks any existing session cookie in the browser (Auth.js throws
`JWTSessionError: no matching decryption secret`), and a random `INTERNAL_AUTH_SECRET`
won't match the backend's default, so the web→backend mint route fails. The canonical
values below match what the repo's own auth tooling uses:
- `NEXTAUTH_SECRET=dev-only-do-not-use-in-prod` — the fallback in `web/scripts/mint-session-cookie.ts` and `mint-playwright-auth.ts`.
- `INTERNAL_AUTH_SECRET=dev-only-internal-auth-do-not-use-in-prod` — the default in `backend/app/config.py` (backend/.env doesn't override it).

```bash
[ -f web/.env.local ] || cat > web/.env.local <<'EOF'
NEXTAUTH_SECRET=dev-only-do-not-use-in-prod
NEXTAUTH_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
INTERNAL_AUTH_SECRET=dev-only-internal-auth-do-not-use-in-prod
EOF
```
If `web/.env.local` already exists but has a **random** `NEXTAUTH_SECRET` (e.g. from a
prior bad run) and the UI shows `JWTSessionError`, reset it to the canonical value above
and restart the web server. Stale browser cookies then decrypt; otherwise the user clears
cookies for `localhost:3000` once.

### 5. Start the four long-lived processes (each in the background)
Pass `DATABASE_URL`/`REDIS_URL` inline so they don't depend on shell exports; the rest
(Anthropic, Tavily, Langfuse) load from `backend/.env` automatically.

**Pass `INTERNAL_AUTH_SECRET` to the backend explicitly, identical to web/.env.local.**
`backend/.env` does NOT set it, so the backend otherwise falls back to its config default —
and if the launching shell happens to have a stale `INTERNAL_AUTH_SECRET` exported (from a
prior session/ambient env you can't see — macOS `ps eww` only shows PATH, so you can't
audit a running process's env), the backend silently uses *that* instead. The web then gets
`403 {"detail":"invalid internal secret"}` on the mint route (surfaces on `/trips`). Setting
it inline on both sides removes the ambiguity. Both must equal
`dev-only-internal-auth-do-not-use-in-prod`.

```bash
# Backend API → :8000
cd backend && DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge" \
  REDIS_URL="redis://localhost:6379" \
  INTERNAL_AUTH_SECRET="dev-only-internal-auth-do-not-use-in-prod" \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend-uvicorn.log 2>&1 &

# Agents service (CrewAI) → :8001
cd agents && DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge" \
  REDIS_URL="redis://localhost:6379" \
  uv run uvicorn trip_agents.service:app --host 0.0.0.0 --port 8001 > /tmp/agents-service.log 2>&1 &

# arq worker (drains crew jobs; lives in backend for DB access)
# CRITICAL: source backend/.env into the env so ANTHROPIC_API_KEY is in os.environ at
# IMPORT time. The agent modules call build_llm() at import; if the key isn't visible then,
# build_llm() returns None, each agent is built with llm=None, and CrewAI silently falls
# back to its OpenAI default → the crew dies with "ValueError: OPENAI_API_KEY is required"
# (surfaces in the UI as "This trip didn't generate"). Relying on pydantic's env_file load
# alone proved timing/state-sensitive (a stray empty repo-root .env once shadowed it).
# `set -a; . ./.env; set +a` exports every backend/.env var without printing secrets.
cd backend && set -a && . ./.env && set +a && \
  DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge" \
  REDIS_URL="redis://localhost:6379" \
  INTERNAL_AUTH_SECRET="dev-only-internal-auth-do-not-use-in-prod" \
  nohup uv run arq app.worker.WorkerSettings > /tmp/backend-worker.log 2>&1 &
# After it boots, REQUIRE 0 warnings: grep -c "ANTHROPIC_API_KEY missing" /tmp/backend-worker.log → 0

# Web PWA → :3000
cd web && nohup pnpm dev > /tmp/web-dev.log 2>&1 &
```

## Smoke test (drive it, don't just launch it)

```bash
curl -s -o /dev/null -w "backend /health -> %{http_code}\n" http://localhost:8000/health   # 200
curl -s -o /dev/null -w "backend /docs   -> %{http_code}\n" http://localhost:8000/docs      # 200
curl -s -o /dev/null -w "agents /run     -> %{http_code}\n" -X POST http://localhost:8001/run # 422 (needs body) = up
curl -s -o /dev/null -w "web /           -> %{http_code}\n" http://localhost:3000/           # 200
docker exec trip-concierge-redis redis-cli ping                                              # PONG
grep "Starting worker for" /tmp/backend-worker.log                                           # worker registered 3 fns

# Internal mint route — proves web↔backend INTERNAL_AUTH_SECRET match (the /trips dependency).
# MUST use a VALID UUID: FastAPI validates the body (422) BEFORE the header secret check,
# so an invalid user_id masks whether the secret is right. Expect 200 with a token.
curl -s -X POST http://localhost:8000/internal/auth/mint-mcp-token \
  -H "Content-Type: application/json" -H "X-Internal-Secret: dev-only-internal-auth-do-not-use-in-prod" \
  -d '{"user_id":"00000000-0000-0000-0000-000000000001"}' -w "\n-> %{http_code} (200=secrets match; 403=mismatch)\n"
```
- `POST /trips` returning **401 "missing token" is correct** — auth is enforced; the route is live.
- To *see* the web app, screenshot via the project's Playwright (the Chrome extension may
  not be connected): launch a tiny script from inside `web/` (so it resolves `playwright`
  from `web/node_modules`), `page.goto('http://localhost:3000/')`, `page.screenshot(...)`,
  then **look at the image**.

## Known-benign noise (do NOT treat as failures)

- **`ANTHROPIC_API_KEY missing — Researcher will be constructed without an LLM`** —
  benign ONLY in a process that never runs the crew (e.g. a transient import). In the
  **worker (and agents service) it is NOT benign**: it means those agents were built with
  `llm=None` and the crew will fall back to OpenAI and die with `OPENAI_API_KEY is required`.
  Requirement: the worker's startup log must show **0** of these
  (`grep -c "ANTHROPIC_API_KEY missing" /tmp/backend-worker.log` → 0). If it shows >0, the
  key wasn't in the env at import — restart the worker with `backend/.env` sourced (step 5).
  Confirm agents hold an LLM:
  `cd agents && uv run python -c "import trip_agents.researcher as r; print(r.researcher.llm is None)"`
  → `False`.
- **LiteLLM `botocore` / bedrock / sagemaker warnings** — unused providers, ignore.
- **OpenTelemetry `Failed to export batch code: 401`** — Langfuse export auth; tracing only,
  does not affect the crew. Ignore unless you're debugging observability.

## What needs real secrets (can't be faked)

- Actual crew kickoff needs a valid `ANTHROPIC_API_KEY` (and Tavily) in `backend/.env`.
- Driving a real plan through the UI needs an authenticated session (magic-link via Resend,
  or Google OAuth) — both need creds in `backend/.env` / `web/.env.local`. Without them the
  stack is up and all endpoints respond, but you can't complete a logged-in trip flow.

## Troubleshooting

- **`/trips` → `mint_mcp_token HTTP 403: invalid internal secret`** — web's
  `INTERNAL_AUTH_SECRET` ≠ the running backend's. Fix: restart the backend with
  `INTERNAL_AUTH_SECRET="dev-only-internal-auth-do-not-use-in-prod"` inline (step 5) and
  confirm `web/.env.local` has the same. Verify with the mint curl above (valid UUID → 200).
  Note the diagnostic trap: a curl with an invalid `user_id` returns 422 *before* the secret
  check, so it does NOT confirm the secret — always use a valid UUID.
- **UI: "This trip didn't generate. ValueError: OPENAI_API_KEY is required"** — the worker
  built its agents with `llm=None` (Anthropic key not in env at import) and CrewAI fell back
  to OpenAI. The project is Anthropic-only; this is never a "set OPENAI_API_KEY" situation.
  Fix: restart the worker with `backend/.env` sourced (step 5), confirm 0 "ANTHROPIC_API_KEY
  missing" warnings in its log, then re-plan (UI "Plan again", or
  `POST /trips/{id}/plan` with a minted token). A correct run shows an "Agent Started:
  Travel Researcher" box within ~30s and no `providers/openai` traceback. Full crew ≈ 9 min.
- **`JWTSessionError: no matching decryption secret`** — `NEXTAUTH_SECRET` changed since the
  browser cookie was minted (e.g. a random value was written). Set it to
  `dev-only-do-not-use-in-prod`, restart web, reload the page (clear `localhost` cookies if
  it persists).
- **Restart a service after changing its env/secret** — env is read at process start. After
  editing `web/.env.local` or a backend secret, the running process keeps the OLD value
  until restarted. (Same class as the `.claude/rules/slice-completion-discipline.md` step-5b
  "running process behind code/config" drift.)
- **Duplicate web servers / port hops to 3001, 3002** — `pnpm dev` forks a `next-server`
  child under a `node next dev` parent; killing by port often hits only the child and the
  parent respawns, or stale parents accumulate across restarts and grab the next free port.
  To get exactly one on :3000: `pkill -f "next dev"; pkill -f "next-server"`, wait 2s,
  confirm `pgrep -fl "next dev|next-server"` is empty, then start one with `nohup pnpm dev &`.

## Teardown

```bash
# stop the four background processes (kill the job PIDs / background task IDs you started)
pkill -f "next dev"; pkill -f "next-server"   # web (parent + child)
# kill the uvicorn (:8000, :8001) and arq worker you started, then:
make db.down            # stops & removes postgres + redis containers
```
