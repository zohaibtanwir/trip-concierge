"""MCP server runtime config.

The MCP server is a thin HTTP client over the backend. Two things to know:

- `backend_url`: where the backend lives. Default is local dev.
- `token_file`: where the user's JWT lives on disk. XDG path so it
  follows the user's existing config conventions; falls back to
  ~/.config/trip-concierge/token when XDG_CONFIG_HOME is unset.

No secrets are read from env — the token comes from the file, the
backend URL is configuration (not a secret). This keeps the MCP
server's runtime surface small.
"""

from __future__ import annotations

import os
from pathlib import Path


def default_token_file() -> Path:
    """XDG-compatible path. Resolved at call time so tests can override
    XDG_CONFIG_HOME via monkeypatch.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "trip-concierge" / "token"
    return Path.home() / ".config" / "trip-concierge" / "token"


def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8000")


def user_email() -> str | None:
    """Read TC_MCP_USER_EMAIL — the user's email for the MCP-side
    magic-link challenge flow (slice 4.1b).

    Returns None if missing or empty — challenges.py treats that as the
    'not configured' branch and surfaces a setup hint to the user via
    the @requires_auth decorator. We don't raise here so the read can be
    safely called on every tool invocation without try/except.

    Per-user config: set in Claude Desktop's MCP server config block.
    See .env.example or CLAUDE.md for the snippet.
    """
    value = os.environ.get("TC_MCP_USER_EMAIL", "").strip()
    return value or None
