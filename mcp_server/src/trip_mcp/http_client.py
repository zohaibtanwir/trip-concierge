"""Thin httpx wrappers for backend calls.

Two flavors:
- `authed_client()`: reads the JWT from disk and injects `x-tc-token`.
  Raises NoTokenError if the token file is missing — the @requires_auth
  decorator in tools/_base.py catches it and triggers the challenge flow.
- `unauthed_client()`: same base_url + timeout, NO Authorization header.
  Used by the magic-link challenge endpoints (POST /auth/mcp/challenge,
  GET /auth/mcp/poll/{code}) which are user-driven and pre-auth.

Slice 4.1b added unauthed_client to support the MCP-side magic-link
challenge flow. Existing tools continue to use authed_client unchanged.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import httpx

from trip_mcp.auth import load_token
from trip_mcp.config import backend_url


@contextmanager
def authed_client() -> Any:
    """Yield an httpx.Client with x-tc-token + base_url pre-set.

    Closes the client on exit. NoTokenError propagates if the token file
    is missing — let the decorator translate it to a user-facing hint.
    """
    token = load_token()
    client = httpx.Client(
        base_url=backend_url(),
        headers={"x-tc-token": token},
        timeout=30.0,
    )
    try:
        yield client
    finally:
        client.close()


@contextmanager
def unauthed_client() -> Any:
    """Yield an httpx.Client with base_url pre-set, NO auth header.

    Used by the slice-4.1b magic-link challenge flow which is pre-auth
    by definition (it exists to obtain a token, not to use one).
    """
    client = httpx.Client(
        base_url=backend_url(),
        timeout=30.0,
    )
    try:
        yield client
    finally:
        client.close()
