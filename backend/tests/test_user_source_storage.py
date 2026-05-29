"""UserSource storage — append_user_source helper + CASCADE integrity.

Slice 3.4b commit 1. Establishes the trip-anchored research-corpus
storage decided in the file-tree session:

- UserSource is a separate table from `sources`, NOT block-anchored.
  Block-anchored Source carries the PRD F6 citation invariant; the
  user-pasted research corpus is structurally different and would
  have produced an M×N anti-pattern if forced into the same table.

- v1.0a does NOT dedup by URL on append. The user pasting the same
  Reddit thread twice may be intentional (content changed since
  last fetch). slice 3.4a's append_constraint dedup-by-(kind,value)
  pattern doesn't carry over because there's no shared notion of
  "same content" across fetches.

Four cases pinning the load-bearing properties:
1. First append persists all fields and returns the row.
2. Multiple appends for one trip accumulate (no dedup, no overwrite).
3. ValueError on missing trip_id (parity with append_constraint shape).
4. CASCADE-delete: deleting the parent Trip removes its UserSources
   without manual cleanup. The FK ondelete='CASCADE' is load-bearing
   for the model lifecycle; without it, deleting a trip would leave
   orphan corpus rows.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.models.user import User
from app.models.user_source import UserSource
from app.services.trip_service import append_user_source


def _make_trip(db: Session) -> Trip:
    user = User(email=f"usrc-{uuid.uuid4()}@test.com", name="UserSource Test")
    db.add(user)
    db.commit()
    db.refresh(user)
    trip = Trip(
        user_id=user.id,
        destination="Goa",
        currency="INR",
        group_size=1,
        pace="balanced",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


def _all_user_sources(db: Session, trip_id: uuid.UUID) -> list[UserSource]:
    stmt = select(UserSource).where(UserSource.trip_id == trip_id).order_by(UserSource.created_at)
    return list(db.execute(stmt).scalars())


def test_append_user_source_persists_url_text_and_content_type(db_session: Session) -> None:
    """First append produces a row with all four content-related fields
    populated and returns the persisted row with a generated UUID id.
    """
    trip = _make_trip(db_session)
    row = append_user_source(
        db_session,
        trip_id=trip.id,
        url="https://reddit.com/r/IndiaTravel/comments/abc/goa_tips",
        raw_text="Goa locals recommend Vinayak Family Restaurant for the prawn curry.",
        content_type="url_fetched",
    )

    assert isinstance(row.id, uuid.UUID)
    assert row.trip_id == trip.id
    assert row.url == "https://reddit.com/r/IndiaTravel/comments/abc/goa_tips"
    assert "Vinayak" in row.raw_text
    assert row.content_type == "url_fetched"
    assert row.fetched_at is not None
    assert row.created_at is not None


def test_append_user_source_does_not_dedup_on_repeat_url(db_session: Session) -> None:
    """v1.0a design choice — no dedup. Two appends of the same URL
    produce two rows. Rationale: user re-fetch may be intentional.
    Pinning this so a future "let's add dedup" refactor surfaces the
    semantic intent rather than silently changing behavior.
    """
    trip = _make_trip(db_session)
    url = "https://example.com/recommendations"
    append_user_source(
        db_session,
        trip_id=trip.id,
        url=url,
        raw_text="Original text.",
        content_type="url_fetched",
    )
    append_user_source(
        db_session,
        trip_id=trip.id,
        url=url,
        raw_text="Updated text after author edited the post.",
        content_type="url_fetched",
    )

    rows = _all_user_sources(db_session, trip.id)
    assert len(rows) == 2, "v1.0a appends without dedup"
    assert rows[0].raw_text == "Original text."
    assert rows[1].raw_text == "Updated text after author edited the post."


def test_append_user_source_raises_on_missing_trip(db_session: Session) -> None:
    """ValueError parity with append_constraint (slice 3.4a commit 1).
    The route layer handles the 404; the helper raises so a programmatic
    caller that forgets to pre-check gets a loud failure, not a silent
    orphan write.
    """
    with pytest.raises(ValueError, match="not found"):
        append_user_source(
            db_session,
            trip_id=uuid.uuid4(),
            url="https://example.com",
            raw_text="x",
            content_type="url_fetched",
        )


def test_user_sources_cascade_delete_with_parent_trip(db_session: Session) -> None:
    """FK ondelete='CASCADE' is load-bearing for the model lifecycle.
    Deleting a Trip must remove its UserSource rows automatically; any
    orphan-row leakage means future trip-id reuse (theoretical with
    gen_random_uuid, but the invariant matters) could leak old research
    into a different trip's view.
    """
    trip = _make_trip(db_session)
    append_user_source(
        db_session,
        trip_id=trip.id,
        url="https://example.com/a",
        raw_text="research a",
        content_type="url_fetched",
    )
    append_user_source(
        db_session,
        trip_id=trip.id,
        url=None,
        raw_text="research b pasted as text by the user",
        content_type="user_text",
    )

    assert len(_all_user_sources(db_session, trip.id)) == 2

    db_session.delete(trip)
    db_session.commit()

    assert len(_all_user_sources(db_session, trip.id)) == 0
