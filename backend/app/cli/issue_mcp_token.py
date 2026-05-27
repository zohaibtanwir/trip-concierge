"""tc-issue-mcp-token — dev CLI for issuing MCP JWTs.

Production magic-link flow lands in slice 4.1. Until then, devs run:

    uv run --project backend tc-issue-mcp-token --email <addr>

The CLI finds or creates the User row, then prints a 90-day JWT to
stdout. Paste it into ~/.config/trip-concierge/token on the dev box
running Claude Desktop and restart MCP.

Dev-only. Not exposed via HTTP. No rate limiting (it's a local script).
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys

from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_session
from app.models.user import User
from app.services.mcp_tokens import issue_token

# Pragmatic email check — covers >99% of real addresses without pulling in
# a full validator dep. Use a real lib (email-validator) only if a real-
# user-facing surface needs it. CLI input is dev-typed; this is enough.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IssueTokenError(Exception):
    """Invalid CLI input."""


def issue_token_for_email(db: Session, *, email: str, secret: str) -> str:
    """Find or create a User by email, issue a JWT, return it.

    Pure function — no I/O beyond the DB session passed in. Easy to test.
    """
    if not _EMAIL_RE.match(email):
        raise IssueTokenError(f"not a valid email: {email!r}")

    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)

    return issue_token(user_id=user.id, secret=secret)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tc-issue-mcp-token",
        description="Dev tool — issue an MCP JWT for a user by email.",
    )
    parser.add_argument("--email", required=True, help="User email address")
    args = parser.parse_args(argv)

    secret = settings.tc_mcp_token_secret
    if not secret or secret == "dev-only-do-not-use-in-prod":
        # Dev default is fine for local CLI use; just log it so it's not silent.
        print(
            "warning: using a dev default for TC_MCP_TOKEN_SECRET — "
            "set the env var before going to prod.",
            file=sys.stderr,
        )

    db_iter = get_session()
    db = next(db_iter)
    try:
        token = issue_token_for_email(db, email=args.email, secret=secret)
    except IssueTokenError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        with contextlib.suppress(StopIteration):
            next(db_iter)

    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
