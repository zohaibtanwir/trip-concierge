.PHONY: setup dev agents.dev test check hooks db.up db.down db.migrate db.reset

# Postgres URL used by `make db.*` targets. Override with `DATABASE_URL=...`.
DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge

setup:
	uv sync                  # workspace sync — provisions backend + agents in one shot
	cd mcp_server && uv sync # not yet a workspace member (joins in slice 3.1)
	cd web && pnpm install
	$(MAKE) hooks

hooks:
	bash scripts/install-hooks.sh

dev:
	@echo "TODO: phase 2.5b+ — wire backend uvicorn, agents service, web pnpm dev, mcp concurrently"

# Run the agents FastAPI service for dev. Slice 2.5b adds the arq worker
# alongside it; for now this is just the sync HTTP surface.
agents.dev:
	cd agents && uv run uvicorn trip_agents.service:app --port 8001 --reload

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

db.down:
	docker compose down

db.migrate:
	cd backend && DATABASE_URL="$(DATABASE_URL)" uv run alembic upgrade head

db.reset:
	@printf "About to DROP and recreate trip_concierge. Type 'yes' to confirm: " && read ans && [ "$$ans" = "yes" ]
	docker exec trip-concierge-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS trip_concierge;"
	docker exec trip-concierge-postgres psql -U postgres -d postgres -c "CREATE DATABASE trip_concierge;"
	$(MAKE) db.migrate
