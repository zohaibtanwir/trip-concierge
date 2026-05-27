"""Aggregate import so Alembic env.py sees every model on `Base.metadata`."""

from app.models.block import Block
from app.models.day import Day
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User

__all__ = ["Block", "Day", "JobRun", "Source", "Trip", "User"]
