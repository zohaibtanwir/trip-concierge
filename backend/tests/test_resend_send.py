"""Unit tests for app.services.resend_send.send_mcp_challenge — slice 4.1b (0h0).

Mocks httpx.AsyncClient. Asserts the Resend POST shape exactly so a
future API drift breaks the test rather than silently shipping broken
email.

This is the SECOND Resend send path in the codebase. The first lives in
web/auth.config.ts:sendMagicLink (slice 4.1). Both target the same
endpoint but with DIFFERENT subject + body so users can distinguish
PWA sign-in from MCP-challenge in their inbox. See trip-concierge-yv9
for the consolidation followup.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_TEST_API_KEY = "re_test_dummy_key"
_TEST_FROM = "auth@tripconcierge.app"
_TEST_TO = "send-test@example.com"
_TEST_URL = "https://test.example.com/auth/mcp/redeem?code=AbCdEfGhIjKlMnOpQrStUv"


def _make_settings():
    from app.config import Settings

    s = Settings()
    s.resend_api_key = _TEST_API_KEY
    s.resend_from_email = _TEST_FROM
    return s


def _make_mock_response(status_code: int = 200, text_body: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text_body
    return resp


def _async_client_factory(post_response: MagicMock):
    """Build a mock that satisfies `async with httpx.AsyncClient(...) as c: ...`.

    Returns (factory_for_patch, the_mock_client_for_assertions).
    """
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=post_response)

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory, mock_client


@pytest.mark.asyncio
async def test_send_posts_to_resend_emails_endpoint() -> None:
    from app.services.resend_send import send_mcp_challenge

    factory, mock_client = _async_client_factory(_make_mock_response(200))
    with patch("app.services.resend_send.httpx.AsyncClient", factory):
        await send_mcp_challenge(
            email=_TEST_TO,
            magic_link_url=_TEST_URL,
            settings=_make_settings(),
        )

    mock_client.post.assert_called_once()
    url = mock_client.post.call_args.args[0]
    assert url == "https://api.resend.com/emails"


@pytest.mark.asyncio
async def test_send_uses_bearer_auth_with_resend_api_key() -> None:
    from app.services.resend_send import send_mcp_challenge

    factory, mock_client = _async_client_factory(_make_mock_response(200))
    with patch("app.services.resend_send.httpx.AsyncClient", factory):
        await send_mcp_challenge(
            email=_TEST_TO,
            magic_link_url=_TEST_URL,
            settings=_make_settings(),
        )

    kwargs = mock_client.post.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == f"Bearer {_TEST_API_KEY}"
    assert kwargs["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_send_body_carries_from_to_mcp_subject_and_url_in_both_bodies() -> None:
    """Subject must be the MCP-specific phrasing (distinguishes from PWA
    'Sign in to Trip Concierge' subject). URL must appear in BOTH html
    and text so HTML-stripping clients still get the link.
    """
    from app.services.resend_send import send_mcp_challenge

    factory, mock_client = _async_client_factory(_make_mock_response(200))
    with patch("app.services.resend_send.httpx.AsyncClient", factory):
        await send_mcp_challenge(
            email=_TEST_TO,
            magic_link_url=_TEST_URL,
            settings=_make_settings(),
        )

    body = mock_client.post.call_args.kwargs["json"]
    assert body["from"] == _TEST_FROM
    assert body["to"] == _TEST_TO
    assert body["subject"] == "Authorize Trip Concierge for Claude Desktop"
    assert _TEST_URL in body["html"]
    assert _TEST_URL in body["text"]


@pytest.mark.asyncio
async def test_send_raises_resend_send_error_on_non_2xx() -> None:
    from app.services.resend_send import ResendSendError, send_mcp_challenge

    factory, _ = _async_client_factory(_make_mock_response(429, "rate limited"))
    with (
        patch("app.services.resend_send.httpx.AsyncClient", factory),
        pytest.raises(ResendSendError, match="429"),
    ):
        await send_mcp_challenge(
            email=_TEST_TO,
            magic_link_url=_TEST_URL,
            settings=_make_settings(),
        )
