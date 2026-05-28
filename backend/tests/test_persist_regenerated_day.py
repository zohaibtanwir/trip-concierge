"""persist_regenerated_day: surgical replace of one day's blocks/sources.

Slice 3.3 commit 4. Unlike persist_audited_plan (destructive replace of
ALL days), this function touches exactly the target day. Other days'
blocks/sources are left untouched — that's the load-bearing property.

Locked-block handling is the worker's responsibility (splice locked
blocks into the input list before calling this function). This persistence
layer just writes whatever blocks list it receives.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.block import Block
from app.models.day import Day
from app.models.source import Source
from app.models.trip import Trip
from app.models.user import User
from app.services.trip_service import persist_audited_plan, persist_regenerated_day


@pytest.fixture
def trip_with_three_days(db_session: Session) -> Trip:
    user = User(email=f"regen-{uuid.uuid4()}@test.com", name="Regen Test")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    trip = Trip(user_id=user.id, destination="Goa", currency="INR")
    db_session.add(trip)
    db_session.commit()
    db_session.refresh(trip)

    # Seed three days, three blocks each, one source per block.
    seed = {
        "days": [
            {
                "day_number": d,
                "date": f"2026-07-{14 + d:02d}",
                "summary": f"Day {d}",
                "blocks": [
                    {
                        "order": o,
                        "type": "venue",
                        "venue_name": f"D{d}-B{o}",
                        "duration_minutes": 60,
                        "est_cost": 500.0,
                        "currency": "INR",
                        "source_urls": [f"https://example.com/d{d}-b{o}"],
                    }
                    for o in (1, 2, 3)
                ],
            }
            for d in (1, 2, 3)
        ]
    }
    persist_audited_plan(db_session, trip.id, seed)
    db_session.refresh(trip)
    return trip


def _new_blocks_for_day(day_number: int) -> list[dict[str, Any]]:
    return [
        {
            "order": o,
            "type": "venue",
            "venue_name": f"NEW-D{day_number}-B{o}",
            "duration_minutes": 90,
            "est_cost": 700.0,
            "currency": "INR",
            "source_urls": [f"https://newsrc.example/d{day_number}-b{o}"],
        }
        for o in (1, 2, 3)
    ]


def test_persist_regenerated_day_replaces_only_target_day(
    db_session: Session, trip_with_three_days: Trip
) -> None:
    """Surgical update: regenerating Day 2 leaves Day 1 and Day 3 untouched."""
    new_blocks = _new_blocks_for_day(2)
    persist_regenerated_day(
        db_session,
        trip_id=trip_with_three_days.id,
        day_number=2,
        blocks=new_blocks,
    )

    # Day 1 unchanged.
    day1_blocks = (
        db_session.execute(
            select(Block)
            .join(Day, Block.day_id == Day.id)
            .where(Day.trip_id == trip_with_three_days.id, Day.day_number == 1)
            .order_by(Block.order)
        )
        .scalars()
        .all()
    )
    assert [b.venue_name for b in day1_blocks] == ["D1-B1", "D1-B2", "D1-B3"]

    # Day 2 replaced.
    day2_blocks = (
        db_session.execute(
            select(Block)
            .join(Day, Block.day_id == Day.id)
            .where(Day.trip_id == trip_with_three_days.id, Day.day_number == 2)
            .order_by(Block.order)
        )
        .scalars()
        .all()
    )
    assert [b.venue_name for b in day2_blocks] == ["NEW-D2-B1", "NEW-D2-B2", "NEW-D2-B3"]
    assert all(b.duration_minutes == 90 for b in day2_blocks), "new duration applied"

    # Day 3 unchanged.
    day3_blocks = (
        db_session.execute(
            select(Block)
            .join(Day, Block.day_id == Day.id)
            .where(Day.trip_id == trip_with_three_days.id, Day.day_number == 3)
            .order_by(Block.order)
        )
        .scalars()
        .all()
    )
    assert [b.venue_name for b in day3_blocks] == ["D3-B1", "D3-B2", "D3-B3"]


def test_persist_regenerated_day_cascades_block_deletion_to_sources(
    db_session: Session, trip_with_three_days: Trip
) -> None:
    """Sources hang off Blocks via FK with ondelete=CASCADE. When the
    target day's blocks are replaced, the old sources must vanish too;
    the new blocks' sources should take their place.
    """
    # Before: Day 2 has 3 blocks × 1 source each = 3 sources.
    before_sources = (
        db_session.execute(
            select(Source)
            .join(Block, Source.block_id == Block.id)
            .join(Day, Block.day_id == Day.id)
            .where(Day.trip_id == trip_with_three_days.id, Day.day_number == 2)
        )
        .scalars()
        .all()
    )
    assert len(before_sources) == 3
    assert all("d2-b" in s.url for s in before_sources)

    persist_regenerated_day(
        db_session,
        trip_id=trip_with_three_days.id,
        day_number=2,
        blocks=_new_blocks_for_day(2),
    )

    after_sources = (
        db_session.execute(
            select(Source)
            .join(Block, Source.block_id == Block.id)
            .join(Day, Block.day_id == Day.id)
            .where(Day.trip_id == trip_with_three_days.id, Day.day_number == 2)
        )
        .scalars()
        .all()
    )
    assert len(after_sources) == 3
    assert all("newsrc.example" in s.url for s in after_sources)


def test_persist_regenerated_day_raises_when_day_missing(
    db_session: Session, trip_with_three_days: Trip
) -> None:
    """If the trip has no Day with that day_number, refuse — surfaces the
    invariant break (worker shouldn't have called us) instead of silently
    inserting blocks under a nonexistent day.
    """
    with pytest.raises(ValueError, match="day 99"):
        persist_regenerated_day(
            db_session,
            trip_id=trip_with_three_days.id,
            day_number=99,
            blocks=_new_blocks_for_day(99),
        )


def test_persist_regenerated_day_preserves_other_columns_on_day_row(
    db_session: Session, trip_with_three_days: Trip
) -> None:
    """The function should touch BLOCKS only — not the Day row's date or
    summary. Day metadata is the worker's call to update if needed.
    """
    persist_regenerated_day(
        db_session,
        trip_id=trip_with_three_days.id,
        day_number=2,
        blocks=_new_blocks_for_day(2),
    )
    day = db_session.execute(
        select(Day).where(Day.trip_id == trip_with_three_days.id, Day.day_number == 2)
    ).scalar_one()
    assert day.summary == "Day 2"
    assert day.date == date_type(2026, 7, 16)
    # Decimal cast to confirm cost types are intact on the new blocks.
    blocks = (
        db_session.execute(select(Block).where(Block.day_id == day.id).order_by(Block.order))
        .scalars()
        .all()
    )
    assert blocks[0].est_cost == Decimal("700.00")
