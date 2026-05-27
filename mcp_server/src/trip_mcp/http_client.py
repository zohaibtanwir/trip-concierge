"""Thin httpx wrapper that attaches the x-tc-token header.

Slice 3.1 doesn't actually call any backend endpoints — tools land in
3.2+. This module exists so the auth-attached pattern is set: every
backend call goes through `authed_client()` which reads the token
from disk and injects the header.

If the token file is missing, `authed_client()` raises NoTokenError —
the @requires_auth decorator in tools/_base.py catches it and surfaces
the dev-CLI hint to the LLM.
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
