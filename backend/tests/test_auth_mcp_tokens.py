"""JWT issuance + verification for the MCP token service.

Stateless HS256 with `sub=user_id` (UUID str), `iat`, `exp=90d`. Signed
with TC_MCP_TOKEN_SECRET — the only trust root in v1.0. The matching
v2.0 followup (per-token revocation via DB lookup) is documented in
backend/app/services/mcp_tokens.py.

These tests are pure-function. No DB, no HTTP. The route + CLI tests
exercise the integration paths.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services.mcp_tokens import (
    InvalidTokenError,
    TokenExpiredError,
    issue_token,
    verify_token,
)

_SECRET = "dev-test-secret-32-bytes-or-more-x"


def test_issue_and_verify_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = issue_token(user_id=user_id, secret=_SECRET)
    claims = verify_token(token, secret=_SECRET)
    assert claims.user_id == user_id


def test_verify_rejects_bad_signature() -> None:
    token = issue_token(user_id=uuid.uuid4(), secret="secret-A-32-bytes-pad-padpadpadpadpad")
    with pytest.raises(InvalidTokenError):
        verify_token(token, secret="secret-B-32-bytes-pad-padpadpadpadpad")


def test_verify_rejects_expired_token() -> None:
    """Token signed with iat in the deep past + a tiny TTL fails as expired."""
    past = datetime.now(UTC) - timedelta(days=120)
    token = issue_token(
        user_id=uuid.uuid4(),
        secret=_SECRET,
        issued_at=past,
        expires_in=timedelta(days=90),
    )
    with pytest.raises(TokenExpiredError):
        verify_token(token, secret=_SECRET)


def test_verify_rejects_malformed_token() -> None:
    with pytest.raises(InvalidTokenError):
        verify_token("not-a-jwt", secret=_SECRET)
