"""tc-issue-mcp-token CLI — dev tool for issuing MCP JWTs without the
production magic-link flow (which lands in slice 4.1).

`uv run --project backend tc-issue-mcp-token --email <addr>` finds or
creates the User, then prints the JWT to stdout. Tests invoke the
underlying Python function (not the subprocess) so they stay fast.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.cli.issue_mcp_token import IssueTokenError, issue_token_for_email
from app.models.user import User
from app.services.mcp_tokens import verify_token

_SECRET = "dev-test-secret-32-bytes-or-more-x"


def test_cli_creates_user_when_email_is_new(db_session: Session) -> None:
    email = f"new-{uuid.uuid4()}@test.com"
    token = issue_token_for_email(db_session, email=email, secret=_SECRET)

    claims = verify_token(token, secret=_SECRET)
    # Find the row the CLI created and assert the JWT subject matches.
    user = db_session.query(User).filter(User.email == email).one()
    assert claims.user_id == user.id


def test_cli_reuses_existing_user(db_session: Session) -> None:
    email = f"existing-{uuid.uuid4()}@test.com"
    existing = User(email=email, name="Existing")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    token = issue_token_for_email(db_session, email=email, secret=_SECRET)
    claims = verify_token(token, secret=_SECRET)
    assert claims.user_id == existing.id

    # Did NOT create a second row.
    count = db_session.query(User).filter(User.email == email).count()
    assert count == 1


def test_cli_rejects_malformed_email(db_session: Session) -> None:
    with pytest.raises(IssueTokenError, match="email"):
        issue_token_for_email(db_session, email="not-an-email", secret=_SECRET)
