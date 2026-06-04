"""Aggregate import so Alembic env.py sees every model on `Base.metadata`."""

from app.models.auth_challenge import AuthChallenge
from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User
from app.models.user_source import UserSource

__all__ = [
    "AuthChallenge",
    "Block",
    "Day",
    "JobRun",
    "Source",
    "Trip",
    "User",
    "UserSource",
]
