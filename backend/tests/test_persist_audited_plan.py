"""persist_audited_plan: writes crew output to Days/Blocks/Sources.

Slice 2.4: this is the only intended write path for trip itineraries.
Slice 2.5 hooks it up to `POST /trips/{id}/plan`; Phase 3 regen tools
will reuse it. Per-block edits in the web UI will use a different,
narrower code path.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User
from app.services.trip_service import persist_audited_plan


@pytest.fixture
def trip(db_session: Session) -> Trip:
    user = User(email=f"persist-{uuid.uuid4()}@test.com", name="Persist Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    trip = Trip(user_id=user.id, destination="Goa", currency="INR")
    db_session.add(trip)
    db_session.commit()
    db_session.refresh(trip)
    return trip


def _audited_two_days() -> dict[str, Any]:
    return {
        "approved": True,
        "currency": "INR",
        "total_cost": 25000.0,
        "per_day_costs": [12000.0, 13000.0],
        "constraints_violated": [],
        "explanation": "",
        "revision_log": [],
        "days": [
            {
                "day_number": 1,
                "date": "2026-07-01",
                "summary": "Arrival + Fontainhas walk",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Fontainhas Heritage Walk",
                        "start_time": "09:00",
                        "duration_minutes": 120,
                        "est_cost": 3000.0,
                        "currency": "INR",
                        "source_urls": [
                            "https://www.viator.com/example",
                            "https://www.getyourguide.com/example",
                        ],
                    },
                    {
                        "order": 2,
                        "type": "meal",
                        "venue_name": "Viva Panjim",
                        "start_time": "13:00",
                        "duration_minutes": 90,
                        "est_cost": 1500.0,
                        "currency": "INR",
                        "source_urls": ["https://www.tripadvisor.com/example"],
                    },
                ],
            },
            {
                "day_number": 2,
                "date": "2026-07-02",
                "summary": "North Goa beaches",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Anjuna Beach",
                        "start_time": "10:00",
                        "duration_minutes": 180,
                        "est_cost": 1800.0,
                        "currency": "INR",
                        "source_urls": ["https://example.com/anjuna"],
                    }
                ],
            },
        ],
    }


def test_persist_writes_expected_row_counts(db_session: Session, trip: Trip) -> None:
    persist_audited_plan(db_session, trip.id, _audited_two_days())

    days = db_session.scalars(select(Day).where(Day.trip_id == trip.id)).all()
    assert len(days) == 2
    assert sorted(d.day_number for d in days) == [1, 2]

    blocks = db_session.scalars(select(Block).join(Day).where(Day.trip_id == trip.id)).all()
    assert len(blocks) == 3  # 2 on day 1, 1 on day 2

    sources = db_session.scalars(
        select(Source).join(Block).join(Day).where(Day.trip_id == trip.id)
    ).all()
    # 2 on Day1-Block1 + 1 on Day1-Block2 + 1 on Day2-Block1 = 4
    assert len(sources) == 4


def test_repersist_overwrites_cleanly(db_session: Session, trip: Trip) -> None:
    persist_audited_plan(db_session, trip.id, _audited_two_days())
    # Re-persist with a smaller plan; should wipe the prior 2 days first.
    smaller: dict[str, Any] = {
        "approved": True,
        "currency": "INR",
        "total_cost": 5000.0,
        "per_day_costs": [5000.0],
        "constraints_violated": [],
        "explanation": "",
        "revision_log": [],
        "days": [
            {
                "day_number": 1,
                "date": None,
                "summary": "Single short day",
                "blocks": [
                    {
                        "order": 1,
                        "type": "rest",
                        "venue_name": "Hotel",
                        "start_time": "20:00",
                        "duration_minutes": 480,
                        "est_cost": 0.0,
                        "currency": "INR",
                        "source_urls": [],
                    }
                ],
            }
        ],
    }
    persist_audited_plan(db_session, trip.id, smaller)

    days = db_session.scalars(select(Day).where(Day.trip_id == trip.id)).all()
    assert len(days) == 1, "re-persist should have wiped the prior 2 days"
    blocks = db_session.scalars(select(Block).join(Day).where(Day.trip_id == trip.id)).all()
    assert len(blocks) == 1
    assert blocks[0].venue_name == "Hotel"


def test_deleting_trip_cascades(db_session: Session, trip: Trip) -> None:
    persist_audited_plan(db_session, trip.id, _audited_two_days())
    trip_id = trip.id
    db_session.delete(trip)
    db_session.commit()

    assert db_session.scalars(select(Day).where(Day.trip_id == trip_id)).all() == []
    # Blocks and Sources should be gone via CASCADE chain.
    assert db_session.scalars(select(Block)).all() == []
    assert db_session.scalars(select(Source)).all() == []
