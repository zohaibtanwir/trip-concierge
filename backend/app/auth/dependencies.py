"""FastAPI dependency: x-tc-token header → authenticated User row.

Use as:

    @router.get(...)
    def handler(user: Annotated[User, Depends(require_mcp_token)]):
        ...

401 on missing or invalid token. 401 (not 403) because we never tell
the caller whether the token shape was bad vs the signature vs expired;
a single response class makes scraping unprofitable.

The secret comes from app.routes.auth._secret (imported lazily to avoid
the cycle: dependencies → routes → dependencies). Tests patch the
function at its source — `patch("app.routes.auth._secret", ...)`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.user import User
from app.services.mcp_tokens import (
    InvalidTokenError,
    TokenExpiredError,
    verify_token,
)


def require_mcp_token(
    x_tc_token: Annotated[str | None, Header(alias="x-tc-token")] = None,
    db: Annotated[Session, Depends(get_session)] = None,  # type: ignore[assignment]
) -> User:
    from app.routes.auth import _secret  # noqa: PLC0415 — break import cycle

    if x_tc_token is None or not x_tc_token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    try:
        claims = verify_token(x_tc_token, secret=_secret())
    except (InvalidTokenError, TokenExpiredError) as e:
        # Don't leak which one failed. Log if you want forensics — never
        # respond with the reason.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from e

    user = db.get(User, claims.user_id)
    if user is None:
        # Token's signature is valid but the user no longer exists (deleted).
        # Treat as 401 — the client should re-issue.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return user
