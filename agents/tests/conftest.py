"""Pytest configuration for agents tests.

Registers the `live` marker and skips it automatically when API keys
aren't present (so CI just skips the live test rather than failing).
Run live tests locally with `pytest -m live` after populating
`backend/.env`.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: hits real Anthropic + Tavily + Langfuse APIs. Skipped unless keys are set.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # If --run-live is not passed AND we're collecting `live` items, skip them
    # unless ANTHROPIC_API_KEY is set in the env (locally).
    import os

    run_live = config.getoption("--run-live", default=False)
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if run_live or has_key:
        return
    skip_live = pytest.mark.skip(reason="needs ANTHROPIC_API_KEY or --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Force-run @pytest.mark.live tests even when no API key is in the shell env.",
    )
