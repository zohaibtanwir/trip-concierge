---
name: stop-app
description: Shut down the full Trip Concierge stack locally — web PWA, backend API, agents service, arq worker, and the Docker containers (Postgres + Redis). Use whenever asked to "stop the app", "shut it down", "bring the stack down", "kill the servers", or to clean up after a run-app session. Covers process teardown, the containers, AND quitting Docker Desktop itself — in the order that avoids stuck jobs and lost logs.
---

# Stop the Trip Concierge app (full stack)

The inverse of `run-app`. "Stop the app" means **the four processes, the two Docker
containers, AND Docker Desktop itself** (`run-app` starts it with `open -a Docker`, so a
full teardown quits it) — leaving Postgres/Redis running is the usual half-done teardown, and
leaving a `next dev` parent alive means the next `run-app` silently hops to port 3001.

**Order is not cosmetic.** Two ordering rules come out of the code, not preference:

1. **Docker goes down LAST.** When the arq worker is signalled, its `asyncio.CancelledError`
   handler (`backend/app/worker.py:317`) writes a `status="cancelled"` JobRun row to
   Postgres and calls `_cleanup_redis_keys()` to delete `trip:{id}:active_job`. Both need
   Postgres and Redis **alive**. Run `make db.down` first and that cleanup fails silently —
   the trip is then wedged (see "Stuck 'running' trip" below).
2. **Backend before worker.** Stopping the API first means nothing new can be enqueued
   while the worker drains.

## ⚠️ Pre-flight: is a crew run in flight?

A full crew kickoff is ~9 minutes and ~$0.40 of real Anthropic + Tavily spend. Killing the
worker mid-run throws that away. Check before you kill anything:

```bash
docker exec trip-concierge-redis redis-cli --scan --pattern 'trip:*:active_job'
```

- **No output** → nothing in flight. Proceed.
- **Any key** → a plan/refine/regen job is queued or running. Tell the user which trip and
  ask whether to wait or cancel. Do not silently kill it.

`trip:{id}:active_job` is exactly the key `GET /trips/{id}/plan/status` reads to decide
`queued` / `running` (`backend/app/routes/plan.py:274`), which is why an orphaned one
wedges the UI.

## Step 1 — Archive the service logs BEFORE killing anything

`run-app` starts every process with `>` redirection, so the **next** startup truncates
these files. Archive first or the forensic window is gone. This mirrors
`.claude/rules/slice-completion-discipline.md` step 5b-1 (`mv`, don't `cp` — preserve
filesystem state for the next run).

```bash
TS=$(date +%Y%m%d-%H%M%S)
for f in backend-uvicorn agents-service backend-worker web-dev; do
  [ -f "/tmp/$f.log" ] && mv "/tmp/$f.log" "/tmp/$f.shutdown-$TS.log" && echo "archived /tmp/$f.log"
done
```

Also catch the legacy names (`/tmp/worker.log`, `/tmp/uvicorn.log`) if they exist — older
sessions used those.

## Step 2 — Stop the four processes, in order

Each process is a `uv run` / `pnpm` **parent plus a child**; the patterns below match both
command lines, so one `pkill` gets the pair. Use these exact patterns — a bare
`pkill -f uvicorn` would kill unrelated projects' servers.

```bash
# 1. Web PWA — parent AND child, else the parent respawns on the next free port
pkill -f "next dev"; pkill -f "next-server"

# 2. Backend API :8000 — stop accepting/enqueueing first
pkill -f "uvicorn app.main:app"

# 3. arq worker — SIGTERM (default), NOT -9. SIGTERM reaches the CancelledError
#    handler that writes the JobRun row and clears the Redis keys. SIGKILL skips it.
pkill -f "arq app.worker.WorkerSettings"
sleep 5   # let the handler write to Postgres/Redis (they're still up — by design)

# 4. Agents service :8001 — after the worker, since the worker calls it
pkill -f "uvicorn trip_agents.service:app"
```

Confirm they're gone before touching Docker:

```bash
pgrep -fl "uvicorn app.main:app|uvicorn trip_agents.service:app|arq app.worker.WorkerSettings|next dev|next-server"
# no output = clean. If a PID survives ~10s, THEN escalate that one pattern with `pkill -9 -f ...`.
```

## Step 3 — Now stop Docker

```bash
make db.down          # docker compose down — stops AND removes both containers
```

**Never `docker compose down -v`.** The `-v` flag deletes the named volumes
`trip_concierge_pgdata` and `trip_concierge_redisdata` — that wipes every trip, user, and
JobRun row and forces a full `make db.migrate` re-run on next boot. Plain `down` keeps the
volumes; data survives to the next `make services.up`. If the user genuinely wants a clean
DB, that's `make db.reset` (which confirms), not `-v`.

### Step 3b — Quit Docker Desktop too

`make db.down` only removes the containers; the Docker Desktop app and its VM keep running
and holding RAM. "Stop the app / including docker" means **the Desktop app is quit as
well** — do not stop at `db.down`.

**First check nothing else on the machine needs the daemon:**

```bash
docker ps -q | wc -l          # MUST be 0 — any other project's containers would be killed
```

- **0** → safe to quit.
- **Non-zero** → other containers are running. Name them (`docker ps --format '{{.Names}}'`)
  and ask before quitting; leave Docker Desktop up otherwise.

```bash
osascript -e 'quit app "Docker Desktop"'    # clean quit, lets the VM shut down properly
# wait for it (usually ~2s):
for i in $(seq 1 45); do docker info >/dev/null 2>&1 || break; sleep 1; done
```

Use `osascript`, not `pkill -f Docker` — a hard kill of the Desktop helpers can leave the
VM's disk image dirty. If `quit app "Docker Desktop"` errors on a name mismatch, fall back
to `osascript -e 'quit app "Docker"'`.

## Step 4 — Verify the teardown

```bash
docker info >/dev/null 2>&1 && echo "daemon STILL RUNNING" || echo "daemon down"   # want: down
pgrep -f "Docker Desktop|com.docker.backend" | wc -l    # want: 0
lsof -ti :3000 -ti :8000 -ti :8001 -ti :5432 -ti :6379  # no output = all ports free
docker volume ls --format '{{.Name}}' | grep trip_concierge   # pgdata + redisdata must SURVIVE
```

Note `docker ps` is useless as a check once the daemon is down (it just errors) — assert on
the daemon being unreachable and 0 Desktop processes instead. Report all four as evidence. "I ran the kill commands" is not confirmation — the port check is.

## Stuck "running" trip (recovery)

Symptom: after a hard kill, the UI spins forever on a trip and
`GET /trips/{id}/plan/status` returns `state="running"` with no worker alive.

Cause: `trip:{id}:active_job` outlived its job. The status route hits the `active is not
None` branch, asks arq for the job (gone), and falls through to `running` — there is no
"job vanished" branch. Redis persists it across `docker compose down` (appendonly + named
volume), so restarting does **not** clear it.

Fix — with Redis up, delete the orphaned keys for that trip:

```bash
docker exec trip-concierge-redis redis-cli --scan --pattern 'trip:*:active_job'   # find it
docker exec trip-concierge-redis redis-cli del "trip:<id>:active_job" "trip:<id>:progress" "trip:<id>:events"
```

The status route then falls through to the JobRun table and reports the real terminal
state. Prevention is Step 2's SIGTERM-not-SIGKILL and Docker-last ordering.

## Troubleshooting

- **Web reappears on :3001 after a restart** — a `next dev` parent survived and grabbed the
  next free port. `pkill -f "next dev"; pkill -f "next-server"`, wait 2s, confirm
  `pgrep -fl "next dev|next-server"` is empty.
- **`make db.down` hangs** — Docker daemon is stopping or already down. `docker info` to
  check; if the daemon is gone the containers are too, so the teardown is effectively done.
- **Port still held after every process is dead** — a stale `uv run` wrapper. Find it with
  `lsof -ti :8000` and kill that PID directly.
- **`pkill` returns exit 1** — that pattern matched nothing, i.e. already stopped. Not an
  error; don't retry or escalate to `-9`.

## Full sequence (copy-paste)

```bash
cd /Users/zohaibtanwir/projects/trip-concierge
docker exec trip-concierge-redis redis-cli --scan --pattern 'trip:*:active_job'   # STOP if non-empty
TS=$(date +%Y%m%d-%H%M%S)
for f in backend-uvicorn agents-service backend-worker web-dev; do
  [ -f "/tmp/$f.log" ] && mv "/tmp/$f.log" "/tmp/$f.shutdown-$TS.log"
done
pkill -f "next dev"; pkill -f "next-server"
pkill -f "uvicorn app.main:app"
pkill -f "arq app.worker.WorkerSettings"
sleep 5
pkill -f "uvicorn trip_agents.service:app"
make db.down
docker ps -q | wc -l                                     # MUST be 0 before the next line
osascript -e 'quit app "Docker Desktop"'
for i in $(seq 1 45); do docker info >/dev/null 2>&1 || break; sleep 1; done
lsof -ti :3000 -ti :8000 -ti :8001 -ti :5432 -ti :6379   # expect no output
docker info >/dev/null 2>&1 && echo "daemon STILL RUNNING" || echo "daemon down"
```
