.PHONY: setup dev test check hooks db.up db.down db.migrate db.reset

# Postgres URL used by `make db.*` targets. Override with `DATABASE_URL=...`.
DATABASE_URL ?= postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge

setup:
	cd backend && uv sync
	cd mcp_server && uv sync
	cd agents && uv sync
	cd web && pnpm install
	$(MAKE) hooks

hooks:
	bash scripts/install-hooks.sh

dev:
	@echo "TODO: phase 1+ — wire backend uvicorn, web pnpm dev, mcp server concurrently"

test:
	cd backend && uv run pytest
	cd mcp_server && uv run pytest
	cd agents && uv run pytest
	cd web && pnpm test

check:
	cd backend && uv run ruff check . && uv run mypy app
	cd mcp_server && uv run ruff check . && uv run mypy server.py
	cd agents && uv run ruff check . && uv run mypy researcher.py local_expert.py crew.py llm.py tasks.py config.py tools
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
