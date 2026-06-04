"""Resend email send — backend-side, MCP-challenge magic-link.

SECOND Resend send path in the codebase. The FIRST lives in
web/auth.config.ts:sendMagicLink (slice 4.1). Both hit
https://api.resend.com/emails with the same auth header + JSON shape,
but DIFFERENT subject + body content so users can distinguish PWA
sign-in from MCP-challenge in their inbox:

  PWA  (slice 4.1):    subject = "Sign in to Trip Concierge"
  MCP  (slice 4.1b):   subject = "Authorize Trip Concierge for Claude Desktop"

If you change either path, update the other. Tracked as
trip-concierge-yv9 for the post-v1.0a consolidation followup.
"""

from __future__ import annotations

import httpx

from app.config import Settings

_RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendSendError(Exception):
    """Resend's API returned a non-2xx response."""


async def send_mcp_challenge(
    *,
    email: str,
    magic_link_url: str,
    settings: Settings,
) -> None:
    """POST the MCP-challenge magic-link email to Resend.

    The HTML and text bodies BOTH include the magic_link_url so clients
    that strip HTML still get a clickable link in the plaintext fallback.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            _RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": email,
                "subject": "Authorize Trip Concierge for Claude Desktop",
                "html": (
                    "<p>Click below to authorize Trip Concierge for your "
                    "Claude Desktop session. The link expires in 10 minutes.</p>"
                    f'<p><a href="{magic_link_url}">Authorize Trip Concierge '
                    "for Claude Desktop</a></p>"
                    "<p>If you didn't request this, you can ignore this email.</p>"
                ),
                "text": (
                    f"Authorize Trip Concierge for Claude Desktop: {magic_link_url}\n\n"
                    "Expires in 10 minutes.\n\n"
                    "If you didn't request this, you can ignore this email."
                ),
            },
        )

    if response.status_code >= 300:
        raise ResendSendError(f"Resend send failed: {response.status_code} {response.text}")
