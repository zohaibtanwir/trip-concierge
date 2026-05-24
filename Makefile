.PHONY: setup dev test check

setup:
	cd backend && uv sync
	cd mcp_server && uv sync

dev:
	@echo "TODO: phase 1+ — wire backend uvicorn, web pnpm dev, mcp server concurrently"

test:
	cd backend && uv run pytest
	cd mcp_server && uv run pytest

check:
	cd backend && uv run ruff check . && uv run mypy app
	cd mcp_server && uv run ruff check . && uv run mypy server.py
