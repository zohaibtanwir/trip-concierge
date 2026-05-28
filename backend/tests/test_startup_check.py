"""Tests for the alembic startup check.

Three scenarios:
1. DB at head → check passes silently (conftest's db_engine fixture
   upgrades the test DB to head, so no patching needed).
2. DB behind head → RuntimeError naming both versions.
3. alembic_version table missing → RuntimeError pointing to db.migrate.

The check is patched at the helper-function level (_head_revision,
_db_revision) so we don't have to actually roll back a real DB.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import Engine

from app.db.startup_check import verify_alembic_at_head


def test_passes_when_db_at_head(db_engine: Engine) -> None:
    """Conftest's session-scoped db_engine fixture runs `command.upgrade
    head` on the test DB, so the live DB IS at head when this test runs.
    The check should pass with no patching.

    Load-bearing assumption: if conftest stops migrating to head, this
    test fails loudly rather than silently passing — that's the right
    failure mode.
    """
    # Should not raise.
    verify_alembic_at_head(engine=db_engine)


def test_raises_clear_error_on_version_mismatch(db_engine: Engine) -> None:
    """Code-side head ahead of DB-side version."""
    with (
        patch("app.db.startup_check._head_revision", return_value="0099"),
        pytest.raises(RuntimeError) as exc_info,
    ):
        verify_alembic_at_head(engine=db_engine)

    msg = str(exc_info.value)
    # Names BOTH versions so the human can act.
    assert "0099" in msg
    # The DB version surfaces too — exact string depends on what's in the
    # test DB, but it'll be the real value (e.g. '0005' once 3.2 is in main).
    assert "code expects" in msg
    # Names the fix.
    assert "make db.migrate" in msg


def test_raises_clear_error_when_alembic_table_missing(db_engine: Engine) -> None:
    """The DB has no alembic_version table at all (fresh, never-migrated DB)."""
    with (
        patch(
            "app.db.startup_check._db_revision",
            side_effect=Exception("UndefinedTable: relation does not exist"),
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        verify_alembic_at_head(engine=db_engine)

    msg = str(exc_info.value)
    assert "alembic_version" in msg
    assert "make db.migrate" in msg
