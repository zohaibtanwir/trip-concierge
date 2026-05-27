"""Token file storage — read / write / clear.

Token lives at $XDG_CONFIG_HOME/trip-concierge/token (or
~/.config/trip-concierge/token). Per-user file, not shared, mode 0600.

These tests use tmp_path so they don't touch the real config dir.
"""

from __future__ import annotations

from pathlib import Path

from trip_mcp.auth import NoTokenError, clear_token, load_token, save_token


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    save_token("abc.def.ghi", token_file=token_file)
    assert load_token(token_file=token_file) == "abc.def.ghi"


def test_load_raises_no_token_error_when_missing(tmp_path: Path) -> None:
    token_file = tmp_path / "absent"
    try:
        load_token(token_file=token_file)
    except NoTokenError:
        pass
    else:
        raise AssertionError("expected NoTokenError when token file is absent")


def test_save_token_has_user_only_permissions(tmp_path: Path) -> None:
    """0600 — token must not be world-readable. Defends against a careless
    `cat ~/.config/trip-concierge/token` in a screen-shared terminal.
    """
    token_file = tmp_path / "token"
    save_token("secret", token_file=token_file)
    mode = token_file.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_clear_token_removes_file(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    save_token("secret", token_file=token_file)
    clear_token(token_file=token_file)
    assert not token_file.exists()
