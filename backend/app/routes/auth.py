"""MCP auth routes — slices 3.1 and 4.1 (mvs).

Two surfaces live in this module:

A. PWA-side mint (slice 4.1 — mvs):

    POST /internal/auth/mint-mcp-token  — called by Next.js Auth.js
                                          signIn callback after a
                                          successful sign-in. Header-
                                          authenticated via the shared
                                          INTERNAL_AUTH_SECRET. Returns
                                          a freshly-minted MCP JWT.

B. Token probe + (future) MCP-side challenge:

    GET /auth/mcp/me                    — token probe; 401 or
                                          {user_id, email}.

    POST /auth/mcp/challenge            — RESERVED for trip-concierge-0h0
                                          (slice 4.1b — MCP-side magic-
                                          link challenge response).
    GET  /auth/mcp/poll/{code}          — RESERVED for 0h0.
    POST /auth/mcp/redeem               — RESERVED for 0h0.

The PWA-side path (A) and the MCP-side challenge path (B) both end up
calling app.services.mcp_tokens.issue_token under the hood. Same
primitive, two entry points. The split is intentional: PWA users sign
in via Auth.js; MCP-only users get a magic link via the challenge flow
because they have no PWA session at that moment.

Rate-limit constants below are spec-locked for ticket 0h0 (slice 4.1b)
and inherited by the slowapi-style middleware that ticket adds. They
do NOT apply to the slice-4.1 mint route: Auth.js itself rate-limits
its own send path (we add per-email throttling in slice 5.4, see
trip-concierge-38t).
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.models.user import User
from app.services.mcp_tokens import issue_token, verify_token

# Rate limit constants — imported by middleware in slice 4.1b (ticket 0h0).
# Format compatible with slowapi (per-endpoint string spec).
# Reasoning for each value lives in the module docstring above.
RATE_LIMIT_CHALLENGE = "5/minute"  # POST /auth/mcp/challenge
RATE_LIMIT_POLL_PER_CODE = "1/2seconds"  # GET /auth/mcp/poll/{code}, max 300/code lifetime
RATE_LIMIT_REDEEM = "5/minute"  # POST /auth/mcp/redeem
RATE_LIMIT_EMAIL = "3/hour"  # email send per IP


router = APIRouter(prefix="/auth/mcp", tags=["auth"])
internal_router = APIRouter(prefix="/internal/auth", tags=["internal-auth"])


def _secret() -> str:
    """Indirection so tests can patch this without monkey-patching settings.

    Pattern: tests do `patch("app.routes.auth._secret", return_value="...")`.
    The dependency layer in app.auth.dependencies imports this function
    (not its return value), so the patch takes effect there too.
    """
    return settings.tc_mcp_token_secret


def _internal_secret() -> str:
    """Same indirection pattern as _secret(), but for the internal-RPC
    auth between Next.js and FastAPI.
    """
    return settings.internal_auth_secret


@router.get("/me")
def me(user: Annotated[User, Depends(require_mcp_token)]) -> dict[str, str]:
    """Probe: confirm a token is valid and identify the bound user."""
    return {"user_id": str(user.id), "email": user.email}


class MintRequest(BaseModel):
    user_id: uuid.UUID


class MintResponse(BaseModel):
    mcp_token: str
    expires_at: datetime


@internal_router.post("/mint-mcp-token", response_model=MintResponse)
def mint_mcp_token(
    payload: MintRequest,
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
) -> MintResponse:
    """Mint an MCP JWT for the given user_id.

    Caller is the Next.js Auth.js signIn callback, NOT a browser. The
    header secret check uses hmac.compare_digest to avoid timing
    distinguishability between "header missing" and "header wrong" —
    both surfaces respond with 403.
    """
    expected = _internal_secret()
    if x_internal_secret is None or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )

    token = issue_token(user_id=payload.user_id, secret=_secret())
    claims = verify_token(token, secret=_secret())
    return MintResponse(mcp_token=token, expires_at=claims.expires_at)
