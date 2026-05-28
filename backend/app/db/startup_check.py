"""Refuse backend startup if the live DB is behind the code's expected schema.

Why this exists: slice 3.2 validation (2026-05-28) surfaced that the dev DB
had drifted three migrations behind code (alembic_version was 0002, code
expected 0005). CI tests passed because `tests/conftest.py:db_engine` runs
`command.upgrade(cfg, "head")` per session against a separate
`trip_concierge_test` DB. The dev DB was never re-migrated; the worker
silently crashed mid-job for the prior two slices and burned ~$0.80 of
real LLM spend producing crew output that couldn't be persisted.

This module fires at backend startup (via FastAPI lifespan). If the DB is
behind, the process exits with a clear instruction. Better to refuse to
start than to serve 500s on every auth-protected route once schema drift
bites — that's worse for users AND harder to diagnose than a startup
banner that says "run make db.migrate."

Tests: see backend/tests/test_startup_check.py — happy path against the
fixture-migrated test DB, plus mismatch path via mock of the head-reader.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from app.db.base import get_engine


def _alembic_config() -> Config:
    """Build an Alembic Config pointing at this project's migrations dir.

    Same Path resolution as conftest.py — backend root is two parents up
    from this file (backend/app/db/startup_check.py).
    """
    backend_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "app" / "db" / "migrations"))
    return cfg


def _head_revision(cfg: Config) -> str | None:
    """The latest revision present in the code's migrations/versions/."""
    return ScriptDirectory.from_config(cfg).get_current_head()


def _db_revision(engine: Engine) -> str | None:
    """The version currently recorded in the DB's alembic_version table."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar()


def verify_alembic_at_head(engine: Engine | None = None) -> None:
    """Raise RuntimeError unless the live DB matches the code's expected head.

    Factored so the head- and db-readers can be patched independently in
    tests without rolling back a real DB. The `engine` arg lets tests pass
    their fixture-built engine; production lifespan calls with no args to
    pick up the env-configured engine via get_engine().
    """
    cfg = _alembic_config()
    head = _head_revision(cfg)

    if engine is None:
        engine = get_engine()
    try:
        db = _db_revision(engine)
    except Exception as e:
        raise RuntimeError(
            "alembic_version table missing or unreadable. "
            "Run `make db.migrate` to initialize the schema. "
            f"(cause: {type(e).__name__}: {e})"
        ) from e

    if db != head:
        raise RuntimeError(
            f"alembic version mismatch — DB at {db!r}, code expects {head!r}. "
            f"Run `make db.migrate` to apply pending migrations.\n"
            f"\n"
            f"This check exists because slice 3.2 validation (2026-05-28) "
            f"discovered the dev DB had drifted three migrations behind code, "
            f"causing silent worker failures and ~$0.80 of unpersisted LLM "
            f"output. CI test DB getting upgrade head per session does NOT "
            f"mean the dev DB advanced — they're different databases."
        )
