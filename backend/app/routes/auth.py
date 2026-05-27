"""MCP auth routes — Slice 3.1.

Today (slice 3.1) this module exposes only ONE endpoint:

    GET /auth/mcp/me   — token probe; 401 or {user_id, email}

The production magic-link flow (clicked URL → email magic link → token)
lands in slice 4.1. The endpoints below are reserved and the rate-limit
numbers are spec-locked here so 4.1 inherits them rather than reinventing:

    POST /auth/mcp/challenge          — 5/IP/min   (cheap to create; bots
                                                    could spam to fill Redis)
    GET  /auth/mcp/poll/{code}        — by-CODE not by-IP: 1 poll per code
                                        per 2 seconds, max 300 polls per
                                        code (matches 10-min lifetime).
                                        Reframes abuse model from
                                        "hammering one code" to "generating
                                        1000 codes" — caught by /challenge
                                        rate limit instead.
    POST /auth/mcp/redeem             — 5/IP/min
    email send (slice 4.1)            — 3 emails per IP per hour

Until those endpoints land, MCP tokens are issued via the dev CLI
(tc-issue-mcp-token --email <addr>) — see app.cli.issue_mcp_token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_mcp_token
from app.config import settings
from app.models.user import User

# Rate limit constants — imported by middleware in slice 4.1.
# Format compatible with slowapi (per-endpoint string spec).
# Reasoning for each value lives in the module docstring above.
RATE_LIMIT_CHALLENGE = "5/minute"  # POST /auth/mcp/challenge
RATE_LIMIT_POLL_PER_CODE = "1/2seconds"  # GET /auth/mcp/poll/{code}, max 300/code lifetime
RATE_LIMIT_REDEEM = "5/minute"  # POST /auth/mcp/redeem (slice 4.1)
RATE_LIMIT_EMAIL = "3/hour"  # email send per IP (slice 4.1)


router = APIRouter(prefix="/auth/mcp", tags=["auth"])


def _secret() -> str:
    """Indirection so tests can patch this without monkey-patching settings.

    Pattern: tests do `patch("app.routes.auth._secret", return_value="...")`.
    The dependency layer in app.auth.dependencies imports this function
    (not its return value), so the patch takes effect there too.
    """
    return settings.tc_mcp_token_secret


@router.get("/me")
def me(user: Annotated[User, Depends(require_mcp_token)]) -> dict[str, str]:
    """Probe: confirm a token is valid and identify the bound user."""
    return {"user_id": str(user.id), "email": user.email}
