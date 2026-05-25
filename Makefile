.PHONY: setup dev test check hooks

setup:
	cd backend && uv sync
	cd mcp_server && uv sync
	cd web && pnpm install
	$(MAKE) hooks

hooks:
	bash scripts/install-hooks.sh

dev:
	@echo "TODO: phase 1+ — wire backend uvicorn, web pnpm dev, mcp server concurrently"

test:
	cd backend && uv run pytest
	cd mcp_server && uv run pytest
	cd web && pnpm test

check:
	cd backend && uv run ruff check . && uv run mypy app
	cd mcp_server && uv run ruff check . && uv run mypy server.py
	cd web && pnpm exec biome check . && pnpm exec tsc --noEmit
