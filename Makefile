.PHONY: setup dev agents.dev backend.worker test check hooks \
        db.up db.down db.migrate db.reset \
        redis.up services.up

# Postgres URL used by `make db.*` targets. Override with `DATABASE_URL=...`.
DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge
REDIS_URL ?= redis://localhost:6379

setup:
	uv sync                  # workspace sync — provisions backend + agents in one shot
	cd mcp_server && uv sync # not yet a workspace member (joins in slice 3.1)
	cd web && pnpm install
	$(MAKE) hooks

hooks:
	bash scripts/install-hooks.sh

dev:
	@echo "TODO: phase 2.5b+ — wire backend uvicorn, agents service, web pnpm dev, mcp concurrently"

# Run the agents FastAPI service for dev. Slice 2.5b's arq worker is a
# separate process (see agents.worker below).
agents.dev:
	cd agents && uv run uvicorn trip_agents.service:app --port 8001 --reload

# Run the arq worker that drains crew-planning jobs from Redis. Lives in
# backend (not agents) because it needs DB access. Connects to REDIS_URL.
# max_jobs is set in WorkerSettings (4 in prod, 1 in dev — override via
# WORKER_MAX_JOBS).
backend.worker:
	cd backend && REDIS_URL="$(REDIS_URL)" uv run arq app.worker.WorkerSettings

test:
	cd backend && uv run pytest
	cd mcp_server && uv run pytest
	cd agents && uv run pytest
	cd web && pnpm test

check:
	cd backend && uv run ruff check . && uv run mypy app
	cd mcp_server && uv run ruff check . && uv run mypy server.py
	cd agents && uv run ruff check . && uv run mypy src/trip_agents
	cd web && pnpm exec biome check . && pnpm exec tsc --noEmit

db.up:
	docker compose up -d postgres
	@echo "Waiting for postgres to be healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' trip-concierge-postgres 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "Postgres ready at $(DATABASE_URL)"

redis.up:
	docker compose up -d redis
	@echo "Waiting for redis to be healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' trip-concierge-redis 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "Redis ready at $(REDIS_URL)"

# Convenience target: bring both up. db.up and redis.up remain as separate
# targets so individual restarts don't drag in the other.
services.up: db.up redis.up

db.down:
	docker compose down

db.migrate:
	cd backend && DATABASE_URL="$(DATABASE_URL)" uv run alembic upgrade head

db.reset:
	@printf "About to DROP and recreate trip_concierge. Type 'yes' to confirm: " && read ans && [ "$$ans" = "yes" ]
	docker exec trip-concierge-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS trip_concierge;"
	docker exec trip-concierge-postgres psql -U postgres -d postgres -c "CREATE DATABASE trip_concierge;"
	$(MAKE) db.migrate
