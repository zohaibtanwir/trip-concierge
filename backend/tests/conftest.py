"""Shared fixtures for backend tests.

`db_engine` is session-scoped: it wipes and migrates the test DB once
per pytest invocation. `db_session` is function-scoped: hands out a
fresh Session and TRUNCATEs all tables after each test so state never
leaks between tests. `client` wires those into a FastAPI TestClient
via dependency override.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session
from app.main import app

DEFAULT_TEST_DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge_test"


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


@pytest.fixture(scope="session")
def db_engine(test_db_url: str) -> Generator[Engine]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session]:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        with db_engine.begin() as conn:
            conn.execute(text("TRUNCATE users, trips RESTART IDENTITY CASCADE;"))


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    def _override() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
