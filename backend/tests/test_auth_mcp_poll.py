"""GET /auth/mcp/poll/{code} — slice 4.1b (0h0) MCP-side poll endpoint.

State machine:
- pending → 200 status=pending, poll_count++, last_polled_at=now
- redeemed (first poll) → 200 status=redeemed + mcp_token,
  row transitions to consumed (one-shot replay protection)
- consumed (subsequent poll) → 410 (gone)
- expired (expires_at < now) → 410, row.status updated to expired
- poll_count >= 300 → 410, row.status set to expired
- not found → 404
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.mcp_tokens import issue_token

_TEST_EMAIL = "poll-test@example.com"
_MCP_SECRET = "dev-test-secret-32-bytes-or-more-x"


def _seed_challenge(
    db: Session,
    *,
    email: str = _TEST_EMAIL,
    code: str = "pollcode22charsxxxxxxx",
    status: str = "pending",
    expires_in_minutes: int = 10,
    poll_count: int = 0,
    mcp_token: str | None = None,
) -> str:
    expires_sql = (
        "now() + INTERVAL '10 minutes'" if expires_in_minutes > 0 else "now() - INTERVAL '1 hour'"
    )
    db.execute(
        text(f"""
            INSERT INTO auth_challenges (code, email, status, poll_count, expires_at)
            VALUES (:code, :email, :status, :poll_count, {expires_sql})
        """),
        {
            "code": code,
            "email": email,
            "status": status,
            "poll_count": poll_count,
        },
    )
    if mcp_token:
        db.execute(
            text("UPDATE auth_challenges SET mcp_token = :t WHERE code = :c"),
            {"t": mcp_token, "c": code},
        )
    db.commit()
    return code


def test_poll_unknown_code_returns_404(client: TestClient) -> None:
    response = client.get("/auth/mcp/poll/this-code-does-not-exist")
    assert response.status_code == 404


def test_poll_pending_returns_pending_status_no_token(
    client: TestClient,
    db_session: Session,
) -> None:
    code = _seed_challenge(db_session)
    response = client.get(f"/auth/mcp/poll/{code}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body.get("mcp_token") is None


def test_poll_pending_increments_poll_count_and_sets_last_polled_at(
    client: TestClient,
    db_session: Session,
) -> None:
    code = _seed_challenge(db_session)
    client.get(f"/auth/mcp/poll/{code}")
    client.get(f"/auth/mcp/poll/{code}")

    row = db_session.execute(
        text("SELECT poll_count, last_polled_at FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.poll_count == 2
    assert row.last_polled_at is not None


def test_poll_redeemed_returns_token_and_transitions_to_consumed(
    client: TestClient,
    db_session: Session,
) -> None:
    """First poll of a redeemed row returns the JWT and transitions
    row.status to consumed (one-shot replay protection)."""
    minted = issue_token(user_id=uuid.uuid4(), secret=_MCP_SECRET)
    code = _seed_challenge(db_session, status="redeemed", mcp_token=minted)

    response = client.get(f"/auth/mcp/poll/{code}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "redeemed"
    assert body["mcp_token"] == minted

    row = db_session.execute(
        text("SELECT status FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.status == "consumed"


def test_poll_consumed_returns_410(
    client: TestClient,
    db_session: Session,
) -> None:
    code = _seed_challenge(db_session, status="consumed")
    response = client.get(f"/auth/mcp/poll/{code}")
    assert response.status_code == 410


def test_poll_expired_returns_410_and_updates_status(
    client: TestClient,
    db_session: Session,
) -> None:
    code = _seed_challenge(db_session, expires_in_minutes=-1)
    response = client.get(f"/auth/mcp/poll/{code}")
    assert response.status_code == 410

    row = db_session.execute(
        text("SELECT status FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.status == "expired"


def test_poll_count_cap_at_300_returns_410(
    client: TestClient,
    db_session: Session,
) -> None:
    """When poll_count reaches 300 (the per-code lifetime cap, matching
    RATE_LIMIT_POLL_PER_CODE = '1/2seconds' × 600s window = 300 polls),
    return 410 and set status to expired."""
    code = _seed_challenge(db_session, poll_count=300)
    response = client.get(f"/auth/mcp/poll/{code}")
    assert response.status_code == 410

    row = db_session.execute(
        text("SELECT status FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.status == "expired"
