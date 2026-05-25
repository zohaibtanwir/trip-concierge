"""Aggregate import so Alembic env.py sees every model on `Base.metadata`."""

from app.models.trip import Trip
from app.models.user import User

__all__ = ["Trip", "User"]
