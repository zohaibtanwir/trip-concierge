"""GET /auth/mcp/me — token verification probe.

In slice 3.1 this is the only public auth endpoint. The clicked-link
flow (challenge / poll / redeem) lands in slice 4.1; the rate-limit
numbers for those endpoints live in code comments in routes/auth.py
so they're inherited as spec.

This route exists so the MCP server (and future PWA) can verify a
token without inventing a probe call. It's also the canary against
patch-path drift in any test that mocks the token-verify dependency.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.mcp_tokens import issue_token

_SECRET = "dev-test-secret-32-bytes-or-more-x"


def test_me_returns_401_without_token_header(client: TestClient) -> None:
    response = client.get("/auth/mcp/me")
    assert response.status_code == 401


def test_me_returns_401_with_bad_token(client: TestClient) -> None:
    response = client.get("/auth/mcp/me", headers={"x-tc-token": "garbage"})
    assert response.status_code == 401


def test_me_returns_200_with_valid_token(client: TestClient, db_session: Session) -> None:
    """End-to-end happy path: real DB user + freshly-issued JWT roundtrips
    through the route and the verify dependency.

    The test patches `app.routes.auth._secret` so production env doesn't
    have to be set in CI. If the patch path drifts, the request gets a 500
    (KeyError on settings) — louder than a silent pass.
    """
    user = User(email=f"me-{uuid.uuid4()}@test.com", name="Me Probe")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = issue_token(user_id=user.id, secret=_SECRET)

    with patch("app.routes.auth._secret", return_value=_SECRET):
        response = client.get("/auth/mcp/me", headers={"x-tc-token": token})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == user.email
