"""POST /auth/mcp/challenge — slice 4.1b (0h0) MCP-side mint trigger.

User-initiated: MCP server requests a challenge for a user's email,
backend creates auth_challenges row + sends magic-link email, returns
code + poll URL.

Behaviors pinned:
1. Happy path: 200 with code (22 chars via secrets.token_urlsafe(16)),
   poll_url ending in /auth/mcp/poll/<code>, expires_at ~10 min future.
2. Creates one auth_challenges row, status=pending, email captured.
3. Calls resend_send.send_mcp_challenge with the built magic-link URL.
4. Bad email format → 422 (Pydantic EmailStr validation).
5. Duplicate-pending under 60s: returns SAME code, NO new row,
   send_mcp_challenge NOT called again (debounce protects inbox).
6. Duplicate-pending over 60s: SAME code, NO new row, BUT send IS
   called again (re-send — original email might be delayed).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_TEST_EMAIL = "magic-test@example.com"


def _challenge_rows_for_email(db: Session, email: str) -> list:
    return list(
        db.execute(
            text(
                "SELECT code, email, status, ip_address, created_at "
                "FROM auth_challenges WHERE email = :e ORDER BY created_at DESC"
            ),
            {"e": email},
        ).fetchall()
    )


def test_challenge_happy_path_returns_code_and_poll_url(
    client: TestClient,
    db_session: Session,
) -> None:
    """First challenge for an email: 200 with code + poll_url + expires_at."""
    # Patch site: service-level import. The service owns the Resend send
    # (so the duplicate-pending debounce logic stays in one place).
    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ) as send_mock:
        response = client.post(
            "/auth/mcp/challenge",
            json={"email": _TEST_EMAIL},
        )

    assert response.status_code == 200, response.text
    body = response.json()

    # secrets.token_urlsafe(16) yields a 22-char base64url string.
    assert "code" in body
    assert len(body["code"]) == 22, f"unexpected code length: {body['code']!r}"

    assert "poll_url" in body
    assert body["poll_url"].endswith(f"/auth/mcp/poll/{body['code']}")

    expires = datetime.fromisoformat(body["expires_at"])
    delta = expires - datetime.now(UTC)
    assert timedelta(minutes=9) < delta < timedelta(minutes=11), (
        f"expires_at delta = {delta} (expected ~10 min)"
    )

    rows = _challenge_rows_for_email(db_session, _TEST_EMAIL)
    assert len(rows) == 1
    assert rows[0].status == "pending"

    send_mock.assert_called_once()


def test_challenge_bad_email_returns_422(client: TestClient) -> None:
    """EmailStr validation rejects non-email values at Pydantic layer."""
    response = client.post("/auth/mcp/challenge", json={"email": "not-an-email"})
    assert response.status_code == 422


def test_challenge_missing_email_returns_422(client: TestClient) -> None:
    response = client.post("/auth/mcp/challenge", json={})
    assert response.status_code == 422


def test_challenge_duplicate_pending_under_60s_reuses_code_skips_send(
    client: TestClient,
    db_session: Session,
) -> None:
    """Second call within 60s: same code, no new row, send NOT called again."""
    # Patch site: service-level import. The service owns the Resend send
    # (so the duplicate-pending debounce logic stays in one place).
    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ) as send_mock:
        r1 = client.post("/auth/mcp/challenge", json={"email": _TEST_EMAIL})
        r2 = client.post("/auth/mcp/challenge", json={"email": _TEST_EMAIL})

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["code"] == r2.json()["code"]

    rows = _challenge_rows_for_email(db_session, _TEST_EMAIL)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"

    assert send_mock.call_count == 1, (
        f"send called {send_mock.call_count} times; expected 1 (debounce)"
    )


def test_challenge_duplicate_pending_over_60s_reuses_code_resends_email(
    client: TestClient,
    db_session: Session,
) -> None:
    """Second call >60s after first: same code, NO new row, BUT send IS
    called again. Re-send protects against delayed delivery of original.
    """
    # Patch site: service-level import. The service owns the Resend send
    # (so the duplicate-pending debounce logic stays in one place).
    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ) as send_mock:
        r1 = client.post("/auth/mcp/challenge", json={"email": _TEST_EMAIL})

        # Backdate created_at so the second call clears the 60s debounce.
        db_session.execute(
            text(
                "UPDATE auth_challenges SET created_at = now() - INTERVAL '61 seconds' "
                "WHERE email = :e"
            ),
            {"e": _TEST_EMAIL},
        )
        db_session.commit()

        r2 = client.post("/auth/mcp/challenge", json={"email": _TEST_EMAIL})

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["code"] == r2.json()["code"]

    rows = _challenge_rows_for_email(db_session, _TEST_EMAIL)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"

    assert send_mock.call_count == 2, (
        f"send called {send_mock.call_count} times; expected 2 (re-send after 60s)"
    )
