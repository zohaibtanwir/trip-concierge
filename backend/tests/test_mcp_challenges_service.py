"""Unit tests for app.services.mcp_challenges — slice 4.1b (0h0).

Tests the create / poll / redeem functions directly, without HTTP. The
route tests cover wiring; these cover the logic + return contracts the
route handler depends on (e.g., redeem_challenge returns a status
string used to pick which HTML variant to render).

Behaviors pinned here that route tests can't easily verify:
- secrets.token_urlsafe(16) → 22-char code shape
- 10-minute TTL constant
- magic_link_url construction format
- redeem_challenge returns 'redeemed' vs 'consumed' for HTML routing
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

_BASE_URL = "https://test.example.com"
_TEST_EMAIL = "service-test@example.com"
_MCP_SECRET = "dev-test-secret-32-bytes-or-more-x"


def _make_settings():
    """Build a Settings instance with Resend creds set.
    Plain attribute assignment works because pydantic-settings allows
    mutation by default (we didn't configure validate_assignment=True).
    """
    from app.config import Settings

    s = Settings()
    s.resend_api_key = "re_test_dummy_key"
    s.resend_from_email = "auth@tripconcierge.app"
    return s


@pytest.mark.asyncio
async def test_create_challenge_generates_22_char_code(db_session: Session) -> None:
    from app.services import mcp_challenges

    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ):
        result = await mcp_challenges.create_challenge(
            db=db_session,
            email=_TEST_EMAIL,
            ip_address="127.0.0.1",
            base_url=_BASE_URL,
            settings=_make_settings(),
        )

    assert len(result.code) == 22, f"got {len(result.code)} chars: {result.code!r}"


@pytest.mark.asyncio
async def test_create_challenge_sets_10_minute_expiry(db_session: Session) -> None:
    from app.services import mcp_challenges

    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ):
        result = await mcp_challenges.create_challenge(
            db=db_session,
            email=_TEST_EMAIL,
            ip_address="127.0.0.1",
            base_url=_BASE_URL,
            settings=_make_settings(),
        )

    delta = result.expires_at - datetime.now(UTC)
    assert timedelta(minutes=9, seconds=30) < delta < timedelta(minutes=10, seconds=30)


@pytest.mark.asyncio
async def test_create_challenge_builds_correct_poll_url(db_session: Session) -> None:
    from app.services import mcp_challenges

    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ):
        result = await mcp_challenges.create_challenge(
            db=db_session,
            email=_TEST_EMAIL,
            ip_address="127.0.0.1",
            base_url=_BASE_URL,
            settings=_make_settings(),
        )

    assert result.poll_url == f"{_BASE_URL}/auth/mcp/poll/{result.code}"


@pytest.mark.asyncio
async def test_create_challenge_sends_magic_link_url_to_resend(
    db_session: Session,
) -> None:
    """The Resend send receives the correctly-built magic-link URL,
    not a different shape (e.g., no extra ?email= query)."""
    from app.services import mcp_challenges

    with patch(
        "app.services.mcp_challenges.send_mcp_challenge",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await mcp_challenges.create_challenge(
            db=db_session,
            email=_TEST_EMAIL,
            ip_address="127.0.0.1",
            base_url=_BASE_URL,
            settings=_make_settings(),
        )

    send_mock.assert_called_once()
    kwargs = send_mock.call_args.kwargs
    assert kwargs["email"] == _TEST_EMAIL
    assert kwargs["magic_link_url"] == f"{_BASE_URL}/auth/mcp/redeem?code={result.code}"


def test_poll_unknown_code_raises_404(db_session: Session) -> None:
    from app.services import mcp_challenges

    with pytest.raises(HTTPException) as exc:
        mcp_challenges.poll_challenge(db=db_session, code="does-not-exist")
    assert exc.value.status_code == 404


def test_poll_pending_returns_pending_status(db_session: Session) -> None:
    from app.services import mcp_challenges

    db_session.execute(
        text(
            "INSERT INTO auth_challenges (code, email, status, expires_at) "
            "VALUES ('pendcode22charsxxxxxxx', :e, 'pending', now() + INTERVAL '10 minutes')"
        ),
        {"e": _TEST_EMAIL},
    )
    db_session.commit()

    result = mcp_challenges.poll_challenge(db=db_session, code="pendcode22charsxxxxxxx")
    assert result.status == "pending"
    assert result.mcp_token is None


def test_poll_redeemed_transitions_row_to_consumed(db_session: Session) -> None:
    """Service contract: first poll of a redeemed row returns the token
    AND mutates the row to status=consumed (one-shot)."""
    from app.services import mcp_challenges

    db_session.execute(
        text(
            "INSERT INTO auth_challenges (code, email, status, mcp_token, expires_at) "
            "VALUES ('redmcode22charsxxxxxxx', :e, 'redeemed', :t, "
            "now() + INTERVAL '10 minutes')"
        ),
        {"e": _TEST_EMAIL, "t": "fake-jwt-string"},
    )
    db_session.commit()

    result = mcp_challenges.poll_challenge(db=db_session, code="redmcode22charsxxxxxxx")
    assert result.status == "redeemed"
    assert result.mcp_token == "fake-jwt-string"

    row = db_session.execute(
        text("SELECT status FROM auth_challenges WHERE code = 'redmcode22charsxxxxxxx'")
    ).fetchone()
    assert row.status == "consumed"


def test_redeem_pending_returns_redeemed_status_string(db_session: Session) -> None:
    """Route handler uses the returned string ('redeemed' vs 'consumed')
    to pick which HTML variant to render."""
    from app.services import mcp_challenges

    db_session.execute(
        text(
            "INSERT INTO auth_challenges (code, email, status, expires_at) "
            "VALUES ('rdpcode22charsxxxxxxx1', :e, 'pending', now() + INTERVAL '10 minutes')"
        ),
        {"e": _TEST_EMAIL},
    )
    db_session.commit()

    status = mcp_challenges.redeem_challenge(
        db=db_session, code="rdpcode22charsxxxxxxx1", secret=_MCP_SECRET
    )
    assert status == "redeemed"


def test_redeem_consumed_returns_consumed_status_string(db_session: Session) -> None:
    """Click after MCP polled — service returns 'consumed' so route renders
    the different 'close this tab' HTML."""
    from app.services import mcp_challenges

    db_session.execute(
        text(
            "INSERT INTO auth_challenges (code, email, status, mcp_token, expires_at) "
            "VALUES ('rdccode22charsxxxxxxx2', :e, 'consumed', 'tok', "
            "now() + INTERVAL '10 minutes')"
        ),
        {"e": _TEST_EMAIL},
    )
    db_session.commit()

    status = mcp_challenges.redeem_challenge(
        db=db_session, code="rdccode22charsxxxxxxx2", secret=_MCP_SECRET
    )
    assert status == "consumed"
