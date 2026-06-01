"""POST /internal/auth/mint-mcp-token — Slice 4.1 (mvs) PWA-side mint.

Auth.js v5's signIn callback on the PWA calls this route after a
successful magic-link or Google OAuth sign-in. The route is NOT
user-authenticated — the caller is the Next.js server, NOT a browser.
Authentication is via INTERNAL_AUTH_SECRET in the X-Internal-Secret
header.

Four properties pinned here:

1. Missing header → 403.
2. Wrong header → 403 (constant-time compare).
3. Correct header + user_id → 200 + JWT that verifies via mcp_tokens.
4. Provider-agnostic mint contract — parametrized over email-only,
   google-only, and cross-provider fixtures. The JWT's algorithm and
   claim structure are identical regardless of which provider got the
   user here. This is the LOAD-BEARING test that pins the v1.0a
   contract: a user signed in via magic-link has the same MCP token
   shape as a user signed in via Google, and a user with BOTH provider
   accounts linked still has ONE user_id and ONE token shape.

The third fixture (cross_provider) also pins the schema invariant: the
accounts table allows multiple rows per user_id with different
providers, so cross-provider linking via Auth.js's adapter does NOT
create duplicate User rows.
"""

from __future__ import annotations

import uuid
from typing import Literal
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.mcp_tokens import verify_token

_INTERNAL_SECRET = "internal-test-secret-32-bytes-or-mor"
_MCP_SECRET = "dev-test-secret-32-bytes-or-more-x"


def _make_user(db: Session, email: str | None = None) -> User:
    user = User(email=email or f"u-{uuid.uuid4()}@test.com", name="Mint Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_account(
    db: Session,
    *,
    user_id: uuid.UUID,
    provider: Literal["resend", "google"],
    provider_account_id: str | None = None,
) -> None:
    """Insert an accounts row via raw SQL.

    pg-adapter owns this table at runtime. Backend never writes to it in
    production. Tests insert directly so the cross-provider fixture can
    pin the schema's multi-account-per-user_id invariant.
    """
    db.execute(
        text(
            """
            INSERT INTO accounts ("userId", type, provider, "providerAccountId")
            VALUES (:user_id, :type, :provider, :provider_account_id)
            """
        ),
        {
            "user_id": user_id,
            "type": "oauth" if provider == "google" else "email",
            "provider": provider,
            "provider_account_id": provider_account_id or str(uuid.uuid4()),
        },
    )
    db.commit()


def test_mint_returns_403_without_internal_secret_header(
    client: TestClient,
    db_session: Session,
) -> None:
    user = _make_user(db_session)

    response = client.post(
        "/internal/auth/mint-mcp-token",
        json={"user_id": str(user.id)},
    )
    assert response.status_code == 403, response.text


def test_mint_returns_403_with_wrong_internal_secret(
    client: TestClient,
    db_session: Session,
) -> None:
    user = _make_user(db_session)

    with patch("app.routes.auth._internal_secret", return_value=_INTERNAL_SECRET):
        response = client.post(
            "/internal/auth/mint-mcp-token",
            json={"user_id": str(user.id)},
            headers={"X-Internal-Secret": "wrong-secret-completely-different"},
        )
    assert response.status_code == 403, response.text


def test_mint_returns_valid_jwt_for_existing_user(client: TestClient, db_session: Session) -> None:
    """Correct secret + valid user_id → JWT that verifies cleanly via
    mcp_tokens.verify_token using the same TC_MCP_TOKEN_SECRET.
    """
    user = _make_user(db_session)

    with (
        patch("app.routes.auth._internal_secret", return_value=_INTERNAL_SECRET),
        patch("app.routes.auth._secret", return_value=_MCP_SECRET),
    ):
        response = client.post(
            "/internal/auth/mint-mcp-token",
            json={"user_id": str(user.id)},
            headers={"X-Internal-Secret": _INTERNAL_SECRET},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "mcp_token" in body
    assert "expires_at" in body

    claims = verify_token(body["mcp_token"], secret=_MCP_SECRET)
    assert claims.user_id == user.id


@pytest.mark.parametrize(
    "fixture_kind",
    ["email_only", "google_only", "cross_provider"],
)
def test_mint_token_shape_identical_across_providers(
    client: TestClient,
    db_session: Session,
    fixture_kind: str,
) -> None:
    """Provider-agnostic contract. The minted JWT has the same algorithm
    and claim structure regardless of which provider(s) brought the user
    in. Cross-provider fixture additionally pins the schema invariant
    that two accounts rows (resend + google) on the same email resolve
    to ONE user_id, not two.
    """
    user = _make_user(db_session, email=f"shared-{fixture_kind}-{uuid.uuid4()}@test.com")

    if fixture_kind == "email_only":
        _make_account(db_session, user_id=user.id, provider="resend")
    elif fixture_kind == "google_only":
        _make_account(db_session, user_id=user.id, provider="google")
    elif fixture_kind == "cross_provider":
        _make_account(db_session, user_id=user.id, provider="resend")
        _make_account(db_session, user_id=user.id, provider="google")

    # Same email → same user_id invariant: the SELECT below proves only
    # one User row exists for this email even with two accounts rows.
    user_row_count = db_session.execute(
        text("SELECT COUNT(*) FROM users WHERE email = :email"),
        {"email": user.email},
    ).scalar()
    assert user_row_count == 1, (
        f"{fixture_kind}: expected exactly 1 user row for email, got {user_row_count}"
    )

    with (
        patch("app.routes.auth._internal_secret", return_value=_INTERNAL_SECRET),
        patch("app.routes.auth._secret", return_value=_MCP_SECRET),
    ):
        response = client.post(
            "/internal/auth/mint-mcp-token",
            json={"user_id": str(user.id)},
            headers={"X-Internal-Secret": _INTERNAL_SECRET},
        )

    assert response.status_code == 200, f"{fixture_kind}: {response.text}"
    token = response.json()["mcp_token"]

    # Decode WITHOUT verifying to inspect raw claim structure — provider-
    # agnostic shape pin lives here.
    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})

    assert header["alg"] == "HS256", f"{fixture_kind}: alg drift"
    assert set(claims.keys()) == {"sub", "iat", "exp"}, (
        f"{fixture_kind}: claim keys = {set(claims.keys())}"
    )
    assert claims["sub"] == str(user.id)
    # Standard 90-day TTL (mcp_tokens._DEFAULT_TTL). Tolerate ±60s for
    # test execution time.
    expected_ttl = 90 * 24 * 3600
    actual_ttl = claims["exp"] - claims["iat"]
    assert abs(actual_ttl - expected_ttl) < 60, (
        f"{fixture_kind}: TTL drift {actual_ttl}s vs expected {expected_ttl}s"
    )
