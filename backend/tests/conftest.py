"""Shared fixtures for backend tests.

`db_engine` is session-scoped: it wipes and migrates the test DB once
per pytest invocation. `db_session` is function-scoped: hands out a
fresh Session and TRUNCATEs all tables after each test so state never
leaks between tests. `client` wires those into a FastAPI TestClient
via dependency override.

`authed_client` adds the slice-3.2 ergonomics: a fresh User row + JWT,
returned as (TestClient with x-tc-token header pre-set, User). For any
route that now requires `Depends(require_mcp_token)`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session
from app.main import app
from app.models.user import User
from app.services.mcp_tokens import issue_token

DEFAULT_TEST_DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge_test"
_TEST_SECRET = "test-secret-32-bytes-or-more-padpad"


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


@pytest.fixture
def authed_client(db_session: Session, client: TestClient) -> Generator[tuple[TestClient, User]]:
    """Yield (client_with_x_tc_token_header, user).

    Creates a fresh User row, mints a JWT against `_TEST_SECRET`, patches
    `app.routes.auth._secret` so the require_mcp_token dependency verifies
    against the same value. The `client` fixture already wires the DB
    session override.

    If the patch path drifts the route will get a 401 (or 500) — tests
    will fail loudly rather than silently bypassing auth.
    """
    user = User(email=f"authed-{uuid.uuid4()}@test.com", name="Authed Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = issue_token(user_id=user.id, secret=_TEST_SECRET)
    client.headers.update({"x-tc-token": token})

    with patch("app.routes.auth._secret", return_value=_TEST_SECRET):
        yield client, user

    # Strip the header so a later test that reuses `client` without auth
    # doesn't accidentally inherit it.
    client.headers.pop("x-tc-token", None)
