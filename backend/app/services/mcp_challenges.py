"""MCP magic-link challenge lifecycle — slice 4.1b (0h0).

Three operations:

  create_challenge(...) — POST /auth/mcp/challenge handler logic
  poll_challenge(...)   — GET /auth/mcp/poll/{code} handler logic
  redeem_challenge(...) — GET /auth/mcp/redeem handler logic (side-effect;
                          returns final status string for HTML routing)

Services raise HTTPException directly per the Q3 approval — the service
is route-coupled by design, the status codes ARE the contract. If we
ever need these from a non-HTTP context, we'd refactor then.
"""

from __future__ import annotations

import ipaddress
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.auth_challenge import AuthChallenge
from app.models.user import User
from app.services.mcp_tokens import issue_token
from app.services.resend_send import send_mcp_challenge

# Lifetime cap matching RATE_LIMIT_POLL_PER_CODE = "1/2seconds" × 600s
# challenge window = 300 polls. Beyond this we treat the code as expired.
MAX_POLLS_PER_CODE = 300

# Window inside which we suppress re-send to the same email. The user
# clicking the MCP tool repeatedly while waiting for the email shouldn't
# spam their inbox; after this window we assume the original email was
# delayed and re-send (reusing the same code).
RESEND_DEBOUNCE_SECONDS = 60


class ChallengeResponse(BaseModel):
    code: str
    poll_url: str
    expires_at: datetime


class PollResponse(BaseModel):
    status: Literal["pending", "redeemed", "consumed", "expired"]
    mcp_token: str | None = None
    expires_at: datetime | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _generate_code() -> str:
    """secrets.token_urlsafe(16) — 22 chars base64url. Same entropy as a
    UUIDv4 (128 bits); plenty for a 10-minute-lifetime artifact.
    """
    return secrets.token_urlsafe(16)


def _safe_ip(host: str | None) -> str | None:
    """Filter the request-client host to a PG-INET-compatible string.

    FastAPI's TestClient sends `request.client.host == "testclient"` which
    PG's INET type rejects. Real prod traffic always presents a parseable
    address. Returning None for non-IP strings is the right default — we'd
    rather lose IP-based forensics for a test/synthetic request than crash
    the route.
    """
    if host is None:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


async def create_challenge(
    *,
    db: Session,
    email: str,
    ip_address: str | None,
    base_url: str,
    settings: Settings,
) -> ChallengeResponse:
    """POST /auth/mcp/challenge handler.

    Duplicate-pending detection:
      - <60s after create: reuse code, NO re-send (debounce inbox spam)
      - >=60s after create: reuse code, RE-SEND (original might be delayed)
    """
    existing = db.execute(
        select(AuthChallenge)
        .where(AuthChallenge.email == email, AuthChallenge.status == "pending")
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None and existing.expires_at > _now():
        # Reuse the same code regardless. Decide whether to re-send.
        send_again = (_now() - existing.created_at).total_seconds() >= RESEND_DEBOUNCE_SECONDS
        magic_link_url = f"{base_url}/auth/mcp/redeem?code={existing.code}"
        if send_again:
            await send_mcp_challenge(
                email=email,
                magic_link_url=magic_link_url,
                settings=settings,
            )
        return ChallengeResponse(
            code=existing.code,
            poll_url=f"{base_url}/auth/mcp/poll/{existing.code}",
            expires_at=existing.expires_at,
        )

    # No reusable pending challenge — create a fresh row.
    code = _generate_code()
    expires_at = _now() + timedelta(minutes=settings.challenge_ttl_minutes)
    row = AuthChallenge(
        code=code,
        email=email,
        ip_address=_safe_ip(ip_address),
        status="pending",
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()

    magic_link_url = f"{base_url}/auth/mcp/redeem?code={code}"
    await send_mcp_challenge(
        email=email,
        magic_link_url=magic_link_url,
        settings=settings,
    )

    return ChallengeResponse(
        code=code,
        poll_url=f"{base_url}/auth/mcp/poll/{code}",
        expires_at=expires_at,
    )


def poll_challenge(*, db: Session, code: str) -> PollResponse:
    """GET /auth/mcp/poll/{code} handler.

    State transitions:
      pending  → 200 status=pending (increment counters)
      redeemed → 200 status=redeemed + token (transition row to consumed)
      consumed → 410
      expired  → 410 (auto-update row status if not yet marked)
      poll>300 → 410 + set status=expired

    not found  → 404
    """
    row = db.execute(select(AuthChallenge).where(AuthChallenge.code == code)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="challenge not found")

    # Auto-expire by clock OR by poll-count cap. Mark row before raising
    # so subsequent reads see the terminal state.
    if row.expires_at < _now() or row.poll_count >= MAX_POLLS_PER_CODE:
        if row.status != "expired":
            row.status = "expired"
            db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="challenge expired")

    if row.status == "consumed":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="challenge already consumed")

    # Mark the poll attempt — counts toward the per-code cap.
    row.poll_count += 1
    row.last_polled_at = _now()

    if row.status == "redeemed":
        # One-shot delivery: return the token and immediately transition
        # to consumed so a leaked code can't replay.
        token = row.mcp_token
        row.status = "consumed"
        db.commit()
        return PollResponse(status="redeemed", mcp_token=token, expires_at=row.expires_at)

    db.commit()
    return PollResponse(status="pending", expires_at=row.expires_at)


def redeem_challenge(
    *,
    db: Session,
    code: str,
    secret: str,
) -> Literal["redeemed", "consumed"]:
    """GET /auth/mcp/redeem handler. Returns the final row status string
    so the route can pick which HTML variant to render:

      redeemed → "Return to Claude Desktop and ask me to retry"
      consumed → "Sign-in complete. You can close this tab."

    Idempotent on browser back/refresh: clicking after status=redeemed
    or status=consumed is a no-op that returns the current status.
    """
    row = db.execute(select(AuthChallenge).where(AuthChallenge.code == code)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid link")

    if row.expires_at < _now():
        if row.status not in {"redeemed", "consumed"}:
            row.status = "expired"
            db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="link expired")

    if row.status == "consumed":
        return "consumed"
    if row.status == "redeemed":
        return "redeemed"
    if row.status != "pending":
        # Defensive: any unknown status indicates corrupt state.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="link already used")

    # Process the redemption: look up / create User, mint JWT, write row.
    user = _get_or_create_user(db, row.email)
    token = issue_token(user_id=user.id, secret=secret)
    row.status = "redeemed"
    row.user_id = user.id
    row.mcp_token = token
    row.redeemed_at = _now()
    db.commit()
    return "redeemed"


def _get_or_create_user(db: Session, email: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
