"""@requires_auth decorator — when no token is stored, the tool returns
a message instructing the user to run the dev CLI.

In slice 3.1 the message is dev-only (CLI flow); slice 4.1 replaces it
with the clicked-link flow. The decorator is the seam that swaps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trip_mcp.tools._base import requires_auth


@pytest.mark.asyncio
async def test_requires_auth_returns_cli_hint_when_no_token(tmp_path: Path) -> None:
    @requires_auth(token_file=tmp_path / "absent")
    async def fake_tool(token: str) -> str:
        return f"called with {token}"

    result = await fake_tool()
    # The message is the only thing Claude Desktop sees. Assert key phrasings
    # the LLM and a human dev both need.
    assert "tc-issue-mcp-token" in result
    assert "trip-concierge" in result  # repo / token-file location


@pytest.mark.asyncio
async def test_requires_auth_passes_token_to_wrapped_function(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("abc.def.ghi")
    token_file.chmod(0o600)

    @requires_auth(token_file=token_file)
    async def fake_tool(token: str) -> str:
        return f"called with {token}"

    result = await fake_tool()
    assert result == "called with abc.def.ghi"
