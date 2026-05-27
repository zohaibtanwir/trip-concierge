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
