"""@requires_auth decorator — the seam between MCP tools and the token.

Slice 3.1 returned _DEV_CLI_HINT on NoTokenError. Slice 4.1b (0h0)
replaces that with the production magic-link challenge flow:

  NoTokenError + TC_MCP_USER_EMAIL missing → "set TC_MCP_USER_EMAIL" hint
  NoTokenError + pending challenge → magic-link URL + "let me know" hint
  NoTokenError + challenge redeemed → save_token(jwt) + retry inner fn
                                       with the now-stored token

The decorator is the only place that knows about the challenge flow;
tools call into authed_client which sees only the resolved token.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from trip_mcp.tools._base import requires_auth


@pytest.mark.asyncio
async def test_requires_auth_passes_token_to_wrapped_function(tmp_path: Path) -> None:
    """Happy path (unchanged from slice 3.1): token file present →
    inner tool function called with the token string.
    """
    token_file = tmp_path / "token"
    token_file.write_text("abc.def.ghi")
    token_file.chmod(0o600)

    @requires_auth(token_file=token_file)
    async def fake_tool(token: str) -> str:
        return f"called with {token}"

    result = await fake_tool()
    assert result == "called with abc.def.ghi"


@pytest.mark.asyncio
async def test_no_token_no_email_surfaces_env_var_hint(tmp_path: Path) -> None:
    """Slice 4.1b case 1: NoTokenError + TC_MCP_USER_EMAIL unset → tool
    response tells the user to set the env var. No magic-link URL.
    """
    from trip_mcp.challenges import ChallengeState

    @requires_auth(token_file=tmp_path / "absent")
    async def fake_tool(token: str) -> str:
        return f"called with {token}"

    no_email_state = ChallengeState(redeemed=False, magic_link_url=None)

    with patch(
        "trip_mcp.tools._base._ensure_challenge_resolved",
        return_value=no_email_state,
    ):
        result = await fake_tool()

    assert "TC_MCP_USER_EMAIL" in result, f"expected env-var-missing hint; got: {result!r}"
    # Don't leak the deprecated dev-CLI hint.
    assert "tc-issue-mcp-token" not in result


@pytest.mark.asyncio
async def test_no_token_pending_challenge_surfaces_url_and_retry_hint(
    tmp_path: Path,
) -> None:
    """Slice 4.1b case 2: NoTokenError + pending challenge → response
    contains the magic-link URL AND the "let me know" retry hint."""
    from trip_mcp.challenges import ChallengeState

    @requires_auth(token_file=tmp_path / "absent")
    async def fake_tool(token: str) -> str:
        return f"called with {token}"

    sample_url = "https://backend.example.com/auth/mcp/redeem?code=XYZ123"
    pending_state = ChallengeState(redeemed=False, magic_link_url=sample_url)

    with patch(
        "trip_mcp.tools._base._ensure_challenge_resolved",
        return_value=pending_state,
    ):
        result = await fake_tool()

    assert sample_url in result, f"expected URL in result; got: {result!r}"
    # The retry hint must use "let me know" phrasing so the LLM infers
    # any natural follow-up ("done", "ok", "try again", "I signed in")
    # as a retry trigger — not a magic phrase the user has to memorize.
    assert "let me know" in result.lower()
    assert "tc-issue-mcp-token" not in result


@pytest.mark.asyncio
async def test_no_token_redeemed_challenge_saves_token_and_calls_inner(
    tmp_path: Path,
) -> None:
    """Slice 4.1b case 3: NoTokenError + challenge redeemed → save_token
    called with the JWT, inner tool function called with the now-stored
    token. The decorator handles the full cold-start-to-success flow in
    a single tool invocation.
    """
    from trip_mcp.challenges import ChallengeState

    inner_calls: list[str] = []

    @requires_auth(token_file=tmp_path / "writable-token")
    async def fake_tool(token: str) -> str:
        inner_calls.append(token)
        return f"called with {token}"

    redeemed_state = ChallengeState(
        redeemed=True,
        magic_link_url=None,
        mcp_token="redeemed.jwt.token",
    )

    saves: list[str] = []

    def fake_save_token(token: str, *, token_file: Path | None = None) -> None:
        saves.append(token)
        # Mimic real save_token behavior so the subsequent load_token
        # inside the decorator finds the token on disk.
        assert token_file is not None
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token)

    with (
        patch(
            "trip_mcp.tools._base._ensure_challenge_resolved",
            return_value=redeemed_state,
        ),
        patch("trip_mcp.tools._base.save_token", side_effect=fake_save_token),
    ):
        result = await fake_tool()

    assert saves == ["redeemed.jwt.token"], f"save_token calls: {saves}"
    assert inner_calls == ["redeemed.jwt.token"], (
        f"inner tool not called with the stored token: {inner_calls}"
    )
    assert result == "called with redeemed.jwt.token"
