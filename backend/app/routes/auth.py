"""MCP auth routes — slices 3.1, 4.1 (mvs), and 4.1b (0h0).

Three surfaces live in this module:

A. PWA-side mint (slice 4.1 — mvs):

    POST /internal/auth/mint-mcp-token  — called by Next.js Auth.js
                                          signIn callback after a
                                          successful sign-in. Header-
                                          authenticated via the shared
                                          INTERNAL_AUTH_SECRET. Returns
                                          a freshly-minted MCP JWT.

B. Token probe (slice 3.1):

    GET /auth/mcp/me                    — token probe; 401 or
                                          {user_id, email}.

C. MCP-side magic-link challenge (slice 4.1b — 0h0):

    POST /auth/mcp/challenge            — MCP server initiates a sign-in
                                          for a user it doesn't have a
                                          token for. Sends magic-link
                                          email; returns code + poll URL.
    GET  /auth/mcp/poll/{code}          — MCP server polls until the
                                          user clicks the link. Returns
                                          the minted JWT once, transitions
                                          row to consumed (replay protect).
    GET  /auth/mcp/redeem               — User clicks the magic link.
                                          Mints JWT, renders HTML success
                                          page. TWO variants by status:
                                          'redeemed' (asks user to retry)
                                          vs 'consumed' (MCP already
                                          polled — close-tab message).

The PWA-side path (A) and the MCP-side challenge path (C) both end up
calling app.services.mcp_tokens.issue_token under the hood. Same
primitive, two entry points.

Rate-limit constants below are spec-locked for surface C and applied
via slowapi decorators. They do NOT apply to the slice-4.1 mint route:
Auth.js itself rate-limits its own send path (we add per-email
throttling in slice 5.4, see trip-concierge-38t).
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.rate_limit import limiter
from app.services import mcp_challenges
from app.services.mcp_tokens import issue_token, verify_token

# Rate-limit constants — spec-locked at slice 4.1 design dialogue,
# applied via slowapi decorators in slice 4.1b (this module).
# Format follows slowapi's per-endpoint string spec.
RATE_LIMIT_CHALLENGE = "5/minute"  # POST /auth/mcp/challenge per IP
RATE_LIMIT_POLL_PER_CODE = "1/2seconds"  # GET /auth/mcp/poll/{code} per IP
RATE_LIMIT_REDEEM = "5/minute"  # GET /auth/mcp/redeem per IP
RATE_LIMIT_EMAIL = "3/hour"  # email send per IP


# Two HTML success-page variants per Q4 tightening: the URL the user
# clicked is the same, but the message differs based on whether the MCP
# server has already polled (status=consumed) or not (status=redeemed).
_SUCCESS_HTML_REDEEMED = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Trip Concierge — Sign-in Complete</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 480px;
           margin: 4rem auto; padding: 1rem; line-height: 1.5; }
    h1 { font-size: 1.5rem; margin: 0 0 1rem 0; }
    p { color: #444; margin: 0; }
  </style>
</head>
<body>
  <h1>Sign-in complete</h1>
  <p>Return to Claude Desktop and ask me to retry your request.</p>
</body>
</html>"""

_SUCCESS_HTML_CONSUMED = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Trip Concierge — Sign-in Complete</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 480px;
           margin: 4rem auto; padding: 1rem; line-height: 1.5; }
    h1 { font-size: 1.5rem; margin: 0 0 1rem 0; }
    p { color: #444; margin: 0; }
  </style>
</head>
<body>
  <h1>Sign-in complete</h1>
  <p>You can close this tab.</p>
</body>
</html>"""


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


# --- Slice 4.1b: MCP-side magic-link challenge ---


class ChallengeRequest(BaseModel):
    email: EmailStr


@router.post("/challenge", response_model=mcp_challenges.ChallengeResponse)
@limiter.limit(RATE_LIMIT_CHALLENGE)
async def create_challenge_endpoint(
    request: Request,
    payload: ChallengeRequest,
    db: Annotated[Session, Depends(get_session)],
) -> mcp_challenges.ChallengeResponse:
    """User-initiated: MCP server requests a challenge for a user's email."""
    return await mcp_challenges.create_challenge(
        db=db,
        email=payload.email,
        ip_address=request.client.host if request.client else None,
        base_url=str(request.base_url).rstrip("/"),
        settings=settings,
    )


@router.get("/poll/{code}", response_model=mcp_challenges.PollResponse)
@limiter.limit(RATE_LIMIT_POLL_PER_CODE)
async def poll_challenge_endpoint(
    request: Request,
    code: str,
    db: Annotated[Session, Depends(get_session)],
) -> mcp_challenges.PollResponse:
    """MCP server polls this until status=redeemed. Returns the JWT once
    and marks status=consumed (one-shot replay protection)."""
    return mcp_challenges.poll_challenge(db=db, code=code)


@router.get("/redeem", response_class=HTMLResponse)
@limiter.limit(RATE_LIMIT_REDEEM)
async def redeem_challenge_endpoint(
    request: Request,
    code: str,
    db: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """User clicks the magic link. Mints JWT (if pending), renders HTML
    success. Idempotent on browser back/refresh — two HTML variants:

      status=redeemed  → "Return to Claude Desktop and ask me to retry"
      status=consumed  → "You can close this tab"
    """
    final_status = mcp_challenges.redeem_challenge(db=db, code=code, secret=_secret())
    html = _SUCCESS_HTML_CONSUMED if final_status == "consumed" else _SUCCESS_HTML_REDEEMED
    return HTMLResponse(content=html, status_code=200)
