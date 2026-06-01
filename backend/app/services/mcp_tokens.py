"""MCP token issue + verify.

Stateless HS256 JWTs. `sub=user_id` (UUID), `iat`, `exp=90d`. Signed
with TC_MCP_TOKEN_SECRET.

# v1.0: stateless JWT, no revocation. The secret IS the trust root.
# Compromise of the secret = boot all sessions via rotation.
# v2.0 followup: add mcp_tokens table with token_hash + revoked_at,
# trade one Redis lookup per call for per-token revocation.

Production entry points (both call issue_token below):
- Slice 4.1 (mvs) — PWA-side. Auth.js signIn callback POSTs to
  /internal/auth/mint-mcp-token in app.routes.auth after a successful
  magic-link or Google OAuth sign-in.
- Slice 4.1b (trip-concierge-0h0) — MCP-side challenge. User without
  a token triggers a tool call; MCP server returns a magic-link URL;
  backend's /auth/mcp/redeem mints the token after the user clicks.

Plus the dev CLI (tc-issue-mcp-token) from slice 3.1 — see
app.cli.issue_mcp_token. CLI is for local dev + ops repair only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

_ALGORITHM = "HS256"
_DEFAULT_TTL = timedelta(days=90)


class InvalidTokenError(Exception):
    """Token signature or structure is invalid."""


class TokenExpiredError(Exception):
    """Token was valid at issue time but has expired."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


def issue_token(
    *,
    user_id: uuid.UUID,
    secret: str,
    issued_at: datetime | None = None,
    expires_in: timedelta = _DEFAULT_TTL,
) -> str:
    """Sign and return a JWT for the given user_id."""
    iat = issued_at or datetime.now(UTC)
    exp = iat + expires_in
    payload = {
        "sub": str(user_id),
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def verify_token(token: str, *, secret: str) -> TokenClaims:
    """Verify signature and expiry. Raise on failure."""
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError(str(e)) from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(str(e)) from e

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as e:
        raise InvalidTokenError(f"missing or malformed sub claim: {e}") from e

    return TokenClaims(
        user_id=user_id,
        issued_at=datetime.fromtimestamp(claims["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )
