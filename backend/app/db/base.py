"""SQLAlchemy declarative base and engine factory.

All ORM models inherit from `Base`. `get_engine()` reads `DATABASE_URL`
at call time so tests can override it via env without touching imports.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def get_engine(url: str | None = None) -> Engine:
    resolved = url or os.environ.get("DATABASE_URL")
    if not resolved:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to backend/.env and fill it in."
        )
    return create_engine(resolved, pool_pre_ping=True)
