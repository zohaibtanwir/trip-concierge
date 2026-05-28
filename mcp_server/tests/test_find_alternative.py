"""find_alternative MCP tool — flow tests with mocked backend.

Single backend call: POST /trips/{id}/blocks/{block_id}/alternative.
Unlike the async tools (refine_trip, regenerate_day, add_constraint),
this one runs synchronously and returns the 3 alternatives INLINE.

The branching on the response body's `kind` field is the load-bearing
UX. The slice-3.4a commit 4 design uses 409 for two distinct states
(active job vs not-ready); status code alone is insufficient — the
tool must branch on the `kind` field.

Five load-bearing tests:
1. Happy path 200 — alternatives rendered with venue names, sources,
   ranking (1/2/3), and the follow-up "which one?" question.
2. 409 with kind="active_job" — surfaces the slice-3.3 label
   ("refinement"), does NOT claim alternatives were found.
3. 409 with kind="not_ready" — branches on state value to produce
   the right next-step message (sub-cases: never_planned, failed).
4. 404 (block not found) — distinct from "trip not found"; tells
   the user to call get_trip to see current blocks.
5. 504 with kind="timeout" — surfaces the elapsed_seconds, asks
   the user (not the LLM) whether to retry.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.find_alternative import find_alternative


def _seed_token(tmp_path: Path) -> Path:
    token_file = tmp_path / "token"
    token_file.write_text("dummy.jwt.token")
    token_file.chmod(0o600)
    return token_file


def _fake_response(*, status_code: int, json_payload: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_payload
    return resp


def _fake_client(*, post_response: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.post = MagicMock(return_value=post_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


def _alternatives_payload() -> dict[str, Any]:
    """Mirrors AlternativesList.model_dump() — the 200 response shape."""
    return {
        "alternatives": [
            {
                "venue_name": f"Alt Venue {i}",
                "type": "meal",
                "duration_minutes": 60,
                "est_cost": 600.0,
                "currency": "INR",
                "source_urls": [f"https://example.com/alt{i}"],
                "rationale": f"Strong fit for vegetarian constraint i={i}",
            }
            for i in range(1, 4)
        ]
    }


@pytest.mark.asyncio
async def test_find_alternative_happy_path_renders_three_ranked_alternatives(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    block_id = uuid.uuid4()
    fake = _fake_client(
        post_response=_fake_response(status_code=200, json_payload=_alternatives_payload()),
    )

    with (
        patch("trip_mcp.tools.find_alternative._token_file", return_value=token_file),
        patch("trip_mcp.tools.find_alternative._http_client", return_value=fake),
    ):
        text = await find_alternative(
            trip_id=trip_id,
            block_id=block_id,
            reason="restaurant closed",
        )

    # POST hit the right URL.
    post_args = fake.post.call_args
    assert post_args.args[0] == f"/trips/{trip_id}/blocks/{block_id}/alternative"
    body = post_args.kwargs.get("json") or post_args.args[1]
    assert body["reason"] == "restaurant closed"

    # All 3 venue names appear with ranking numerals.
    assert "Alt Venue 1" in text
    assert "Alt Venue 2" in text
    assert "Alt Venue 3" in text
    assert "1." in text and "2." in text and "3." in text

    # Source URL surfaces — load-bearing for verifiability.
    assert "https://example.com/alt1" in text

    # Follow-up routing — the user picks, we follow up with refine_trip.
    assert "which" in text.lower() or "pick" in text.lower()

    # Slice 3.3 prohibition discipline — no "best"/"perfect" superlatives
    # in the wrapping text (the rationale itself may say "strong fit", but
    # OUR rendering must not.)
    assert "perfect" not in text.lower()
    # "best, first" is the wrapping language for the ranking — that's OK
    # as a ranking signal. Forbidden is claiming a venue IS the best.
    assert "is the best" not in text.lower()


@pytest.mark.asyncio
async def test_find_alternative_409_active_job_surfaces_kind_label(
    tmp_path: Path,
) -> None:
    """409 + kind="active_job" → distinct UX: tell the user another job
    is running, route to get_trip. Must NOT claim alternatives were
    found.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=409,
            json_payload={
                "detail": "a refinement job is already in progress...",
                "kind": "active_job",
                "active_job_id": "refine-existing",
                "active_job_kind": "refine",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.find_alternative._token_file", return_value=token_file),
        patch("trip_mcp.tools.find_alternative._http_client", return_value=fake),
    ):
        text = await find_alternative(trip_id=uuid.uuid4(), block_id=uuid.uuid4(), reason=None)

    # Surfaces the in-flight job kind label.
    assert "refinement" in text.lower()
    # Routes user back to get_trip.
    assert "get_trip" in text
    # No alternatives claimed.
    assert "Alt Venue" not in text
    assert "1." not in text
    # Prohibition discipline.
    assert "found" not in text.lower() or "couldn't" in text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_phrase"),
    [
        ("never_planned", "hasn't been planned"),
        ("failed", "didn't complete"),
    ],
)
async def test_find_alternative_409_not_ready_branches_on_state(
    tmp_path: Path,
    state: str,
    expected_phrase: str,
) -> None:
    """409 + kind="not_ready" + state → branch to the right next-step.
    Mirrors format_regenerate_day_not_ready's state-aware branching.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=409,
            json_payload={
                "detail": "trip not ready for alternatives",
                "kind": "not_ready",
                "state": state,
            },
        ),
    )

    with (
        patch("trip_mcp.tools.find_alternative._token_file", return_value=token_file),
        patch("trip_mcp.tools.find_alternative._http_client", return_value=fake),
    ):
        text = await find_alternative(trip_id=uuid.uuid4(), block_id=uuid.uuid4(), reason=None)

    assert expected_phrase in text.lower(), f"state={state} should surface '{expected_phrase}'"
    assert "Alt Venue" not in text  # no alternatives claimed
    # Slice 3.3 prohibition discipline — name the state plainly.
    for softer in ("almost there", "still working on it", "not quite finished"):
        assert softer not in text.lower()


@pytest.mark.asyncio
async def test_find_alternative_404_block_not_found_routes_to_get_trip(
    tmp_path: Path,
) -> None:
    """Distinct from "trip not found" (no formatter overlap). The block
    not being on this trip means get_trip will show current blocks —
    that's the next step the LLM should suggest.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=404,
            json_payload={"detail": "block not found on this trip"},
        ),
    )

    with (
        patch("trip_mcp.tools.find_alternative._token_file", return_value=token_file),
        patch("trip_mcp.tools.find_alternative._http_client", return_value=fake),
    ):
        text = await find_alternative(trip_id=uuid.uuid4(), block_id=uuid.uuid4(), reason=None)

    assert "block" in text.lower()
    assert "get_trip" in text  # routes to current-blocks lookup
    assert "Alt Venue" not in text


@pytest.mark.asyncio
async def test_find_alternative_504_timeout_surfaces_elapsed_and_asks_user(
    tmp_path: Path,
) -> None:
    """504 + kind="timeout" + elapsed_seconds → honest timeout report
    + user-facing "try again?" question (NOT automatic retry).
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        post_response=_fake_response(
            status_code=504,
            json_payload={
                "detail": "find_alternative timed out after 90 seconds",
                "kind": "timeout",
                "elapsed_seconds": 90.0,
                "trip_id": "x",
                "block_id": "y",
            },
        ),
    )

    with (
        patch("trip_mcp.tools.find_alternative._token_file", return_value=token_file),
        patch("trip_mcp.tools.find_alternative._http_client", return_value=fake),
    ):
        text = await find_alternative(trip_id=uuid.uuid4(), block_id=uuid.uuid4(), reason=None)

    # Names "timeout"/"timed out" plainly — no softer language.
    assert "timed out" in text.lower() or "timeout" in text.lower()
    # Surfaces the elapsed time so the user knows the scale.
    assert "90" in text
    # Puts retry choice on the user — does NOT auto-retry.
    assert "try again" in text.lower() or "retry" in text.lower()
    # Slice 3.3 prohibition discipline.
    assert "almost" not in text.lower()
    assert "Alt Venue" not in text  # no fabricated alternatives
