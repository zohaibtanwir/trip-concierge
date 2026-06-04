"""GET /auth/mcp/redeem?code=... — slice 4.1b (0h0) MCP magic-link landing.

User clicks the magic link from their email. Backend validates code,
looks up/creates User, mints MCP JWT, updates auth_challenges row,
renders HTML success page.

TWO HTML SUCCESS VARIANTS (Q4 tightening):
- _SUCCESS_HTML_REDEEMED: contains "ask me to retry" — shown when
  row.status is pending (just redeemed) OR redeemed (idempotent
  second click before MCP polled).
- _SUCCESS_HTML_CONSUMED: contains "close this tab" — shown when
  row.status is already consumed (MCP polled, token delivered).

Idempotent on browser back / refresh — second click never errors.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.mcp_tokens import verify_token

_TEST_EMAIL = "redeem-test@example.com"
_MCP_SECRET = "dev-test-secret-32-bytes-or-more-x"


def _seed_challenge(
    db: Session,
    *,
    email: str = _TEST_EMAIL,
    code: str = "redeemcode22charsxxxx1",
    status: str = "pending",
    expires_in_minutes: int = 10,
    mcp_token: str | None = None,
) -> str:
    expires_sql = (
        "now() + INTERVAL '10 minutes'" if expires_in_minutes > 0 else "now() - INTERVAL '1 hour'"
    )
    db.execute(
        text(f"""
            INSERT INTO auth_challenges (code, email, status, expires_at)
            VALUES (:code, :email, :status, {expires_sql})
        """),
        {"code": code, "email": email, "status": status},
    )
    if mcp_token:
        db.execute(
            text("UPDATE auth_challenges SET mcp_token = :t WHERE code = :c"),
            {"t": mcp_token, "c": code},
        )
    db.commit()
    return code


def test_redeem_unknown_code_returns_404(client: TestClient) -> None:
    response = client.get("/auth/mcp/redeem", params={"code": "nope"})
    assert response.status_code == 404


def test_redeem_expired_returns_410(
    client: TestClient,
    db_session: Session,
) -> None:
    code = _seed_challenge(db_session, expires_in_minutes=-1)
    response = client.get("/auth/mcp/redeem", params={"code": code})
    assert response.status_code == 410


def test_redeem_pending_creates_user_mints_token_renders_redeemed_html(
    client: TestClient,
    db_session: Session,
) -> None:
    """First valid click on a pending challenge:
    - transitions status pending → redeemed
    - creates User row with row.email
    - mints MCP JWT via mcp_tokens.issue_token
    - renders the 'ask me to retry' HTML success page
    """
    code = _seed_challenge(db_session)

    with patch("app.routes.auth._secret", return_value=_MCP_SECRET):
        response = client.get("/auth/mcp/redeem", params={"code": code})

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]
    text_lower = response.text.lower()
    assert "ask me to retry" in text_lower
    assert "close this tab" not in text_lower

    row = db_session.execute(
        text("SELECT status, mcp_token, user_id, redeemed_at FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.status == "redeemed"
    assert row.mcp_token is not None
    assert row.user_id is not None
    assert row.redeemed_at is not None

    user = db_session.execute(
        text("SELECT id, email FROM users WHERE email = :e"),
        {"e": _TEST_EMAIL},
    ).fetchone()
    assert user is not None
    assert user.id == row.user_id

    claims = verify_token(row.mcp_token, secret=_MCP_SECRET)
    assert claims.user_id == user.id


def test_redeem_pending_with_existing_user_reuses_not_creates(
    client: TestClient,
    db_session: Session,
) -> None:
    """If a User row already exists for this email (e.g. prior PWA sign-in),
    redeem links auth_challenges to that User; no duplicate row.
    """
    existing = User(email=_TEST_EMAIL, name="Pre-existing")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    code = _seed_challenge(db_session)

    with patch("app.routes.auth._secret", return_value=_MCP_SECRET):
        response = client.get("/auth/mcp/redeem", params={"code": code})

    assert response.status_code == 200, response.text

    user_count = db_session.execute(
        text("SELECT COUNT(*) FROM users WHERE email = :e"),
        {"e": _TEST_EMAIL},
    ).scalar()
    assert user_count == 1, f"expected 1 user, got {user_count}"

    row = db_session.execute(
        text("SELECT user_id FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.user_id == existing.id


def test_redeem_idempotent_status_redeemed_second_click_renders_redeemed_html(
    client: TestClient,
    db_session: Session,
) -> None:
    """Browser back/refresh after a successful redeem: row is already
    status=redeemed (MCP hasn't polled yet). Second click renders the
    SAME HTML; row not modified.
    """
    code = _seed_challenge(db_session, status="redeemed", mcp_token="dummy-token")

    response = client.get("/auth/mcp/redeem", params={"code": code})
    assert response.status_code == 200, response.text
    assert "ask me to retry" in response.text.lower()
    assert "close this tab" not in response.text.lower()

    row = db_session.execute(
        text("SELECT status, mcp_token FROM auth_challenges WHERE code = :c"),
        {"c": code},
    ).fetchone()
    assert row.status == "redeemed"
    assert row.mcp_token == "dummy-token"


def test_redeem_status_consumed_renders_consumed_html(
    client: TestClient,
    db_session: Session,
) -> None:
    """Click AFTER the MCP server has polled (status=consumed): show the
    'close this tab' HTML variant. Confirms the route distinguishes
    'MCP hasn't picked up yet' from 'MCP already picked up'.
    """
    code = _seed_challenge(db_session, status="consumed", mcp_token="dummy-token")

    response = client.get("/auth/mcp/redeem", params={"code": code})
    assert response.status_code == 200, response.text
    text_lower = response.text.lower()
    assert "close this tab" in text_lower
    assert "ask me to retry" not in text_lower
