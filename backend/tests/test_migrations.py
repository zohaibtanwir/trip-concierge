"""Verify that `alembic upgrade head` produces the expected schema.

Runs against the dedicated test DB pointed at by TEST_DATABASE_URL,
default `postgresql+psycopg://postgres:postgres@localhost:5432/
trip_concierge_test`. The test wipes the public schema before
migrating so it is order-independent and idempotent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

DEFAULT_TEST_DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge_test"


@pytest.fixture
def alembic_cfg(tmp_path: Path) -> Config:
    """Alembic Config pointed at a temp working dir + the test DB URL."""
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "app" / "db" / "migrations"))
    db_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _wipe(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()


def test_migration_creates_users_and_trips_tables(alembic_cfg: Config) -> None:
    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    _wipe(db_url)

    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert "users" in tables, f"users table missing; got {sorted(tables)}"
    assert "trips" in tables, f"trips table missing; got {sorted(tables)}"
