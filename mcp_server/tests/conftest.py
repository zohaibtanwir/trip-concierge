"""Shared mcp_server test fixtures.

Module-level state in src/trip_mcp/challenges.py (_pending) can leak
between test files. test_challenges.py exercises that state machine
deliberately and clears between its own tests; tool tests need the
same reset or they inherit a stale _pending and try to POLL a real
backend on every NoTokenError path (CI fails with ConnectError;
locally the symptom depends on test-collection order).

Autouse conftest fixture covers ALL tests, not just one file.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_challenge_module_state() -> None:
    """Reset trip_mcp.challenges._pending before every test."""
    from trip_mcp import challenges

    challenges._clear_pending()
