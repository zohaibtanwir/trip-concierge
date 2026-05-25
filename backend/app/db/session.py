"""SQLAlchemy session factory + FastAPI dependency.

Engine is lazily constructed on first call so tests can set DATABASE_URL
after import. Tests override `get_session` via FastAPI's dependency
overrides — see backend/tests/conftest.py.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import get_engine

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure() -> sessionmaker[Session]:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = get_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _SessionLocal


def get_session() -> Generator[Session]:
    factory = _ensure()
    session = factory()
    try:
        yield session
    finally:
        session.close()
