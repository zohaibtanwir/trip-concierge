"""Token storage — read / write / clear the MCP JWT from disk.

Token lives at the path returned by config.default_token_file(),
typically ~/.config/trip-concierge/token. Permissions: 0600.

Slice 3.1 only reads from disk; writing is a future-slice thing once
the production magic-link flow lands. The save_token / clear_token
functions exist now so the file shape is settled.
"""

from __future__ import annotations

import os
from pathlib import Path

from trip_mcp.config import default_token_file


class NoTokenError(Exception):
    """Raised when the token file is missing or empty."""


def load_token(*, token_file: Path | None = None) -> str:
    path = token_file or default_token_file()
    if not path.exists():
        raise NoTokenError(f"token file not found: {path}")
    content = path.read_text().strip()
    if not content:
        raise NoTokenError(f"token file is empty: {path}")
    return content


def save_token(token: str, *, token_file: Path | None = None) -> None:
    """Write the token to disk with 0600 permissions.

    Creates parent dirs as needed. Overwrites without prompt.
    """
    path = token_file or default_token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token)
    os.chmod(path, 0o600)


def clear_token(*, token_file: Path | None = None) -> None:
    """Remove the token file. No-op if it doesn't exist."""
    path = token_file or default_token_file()
    if path.exists():
        path.unlink()
