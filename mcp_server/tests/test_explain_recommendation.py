"""explain_recommendation MCP tool — flow tests with mocked backend.

Slice 3.4b commit 4. Single backend call: GET /trips/{id}/explain/
{block_id}. Pure-read tool — no LLM call, no outbound work, no writes.

The load-bearing UX detail is the **gap-surfacing branch** when the
backend returns rationale=null. The tool MUST render the literal
qek-message language ("The Researcher's per-block rationale wasn't
captured for this venue") for description-↔-tool-response lockstep
per §4.8. A future formatter wording drift breaks this test.

Five load-bearing tests:
1. Happy path with rationale (string) → format_explain_with_rationale.
2. Gap path with rationale=null → format_explain_with_gap, literal
   qek language present.
3. user_source_matches non-empty → provenance line present.
4. 404 trip not found → routes to create_trip.
5. 404 block not found on this trip → routes to get_trip
   (defends against UUID hallucination at presentation layer).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from trip_mcp.tools.explain_recommendation import explain_recommendation


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


def _fake_client(*, get_response: MagicMock) -> MagicMock:
    fake = MagicMock()
    fake.get = MagicMock(return_value=get_response)
    fake.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake.__exit__ = lambda self, *a: None  # type: ignore[method-assign]
    return fake


def _explain_body_with_rationale() -> dict[str, Any]:
    return {
        "block_id": "block-1",
        "venue_name": "Anjuna Beach",
        "block_type": "venue",
        "rationale": (
            "Goa's most iconic sunset beach — beats Calangute for the "
            "laid-back vibe the user asked for."
        ),
        "sources": [
            {
                "url": "https://reddit.com/r/IndiaTravel/anjuna",
                "excerpt": "Locals say Anjuna is the best for sunsets",
                "confidence_score": 0.85,
            },
        ],
        "user_source_matches": [],
    }


def _explain_body_gap_path() -> dict[str, Any]:
    body = _explain_body_with_rationale()
    body["rationale"] = None
    return body


@pytest.mark.asyncio
async def test_explain_recommendation_happy_path_renders_rationale_and_sources(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    trip_id = uuid.uuid4()
    block_id = uuid.uuid4()
    fake = _fake_client(
        get_response=_fake_response(status_code=200, json_payload=_explain_body_with_rationale()),
    )

    with (
        patch("trip_mcp.tools.explain_recommendation._token_file", return_value=token_file),
        patch("trip_mcp.tools.explain_recommendation._http_client", return_value=fake),
    ):
        text = await explain_recommendation(trip_id=trip_id, block_id=block_id)

    # GET hit the right URL.
    get_args = fake.get.call_args
    assert get_args.args[0] == f"/trips/{trip_id}/explain/{block_id}"

    # Body renders venue name + rationale + sources.
    assert "Anjuna Beach" in text
    assert "Goa's most iconic" in text
    assert "https://reddit.com/r/IndiaTravel/anjuna" in text
    # No formatter-level prohibition on excerpt superlatives — see the
    # parallel comment in test_responses.py
    # test_explain_with_rationale_renders_*. Discipline lives at §4.8.


@pytest.mark.asyncio
async def test_explain_recommendation_gap_path_renders_literal_qek_message(
    tmp_path: Path,
) -> None:
    """Lockstep with §4.8 description. The literal "rationale wasn't
    captured" wording must appear; if it drifts in the formatter,
    description instructions misalign with tool output.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        get_response=_fake_response(status_code=200, json_payload=_explain_body_gap_path()),
    )

    with (
        patch("trip_mcp.tools.explain_recommendation._token_file", return_value=token_file),
        patch("trip_mcp.tools.explain_recommendation._http_client", return_value=fake),
    ):
        text = await explain_recommendation(trip_id=uuid.uuid4(), block_id=uuid.uuid4())

    # Lockstep literal — must match §4.8 description verbatim.
    assert "rationale wasn't captured" in text, (
        "gap-text wording must match §4.8 description exactly so the LLM's "
        "routing instructions align with what it sees in the tool response"
    )
    # Sources still rendered.
    assert "Anjuna Beach" in text
    assert "https://reddit.com/r/IndiaTravel/anjuna" in text


@pytest.mark.asyncio
async def test_explain_recommendation_surfaces_user_source_provenance(
    tmp_path: Path,
) -> None:
    token_file = _seed_token(tmp_path)
    body = _explain_body_with_rationale()
    body["user_source_matches"] = [
        {
            "user_source_id": str(uuid.uuid4()),
            "url": "https://reddit.com/r/IndiaTravel/anjuna",
        }
    ]
    fake = _fake_client(
        get_response=_fake_response(status_code=200, json_payload=body),
    )

    with (
        patch("trip_mcp.tools.explain_recommendation._token_file", return_value=token_file),
        patch("trip_mcp.tools.explain_recommendation._http_client", return_value=fake),
    ):
        text = await explain_recommendation(trip_id=uuid.uuid4(), block_id=uuid.uuid4())

    # Provenance line names the URL the user pasted.
    lower = text.lower()
    assert "your" in lower and ("research" in lower or "reddit" in lower)


@pytest.mark.asyncio
async def test_explain_recommendation_404_trip_routes_to_create_trip(tmp_path: Path) -> None:
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        get_response=_fake_response(
            status_code=404,
            json_payload={"detail": "trip not found"},
        ),
    )

    with (
        patch("trip_mcp.tools.explain_recommendation._token_file", return_value=token_file),
        patch("trip_mcp.tools.explain_recommendation._http_client", return_value=fake),
    ):
        text = await explain_recommendation(trip_id=uuid.uuid4(), block_id=uuid.uuid4())

    assert "couldn't find" in text.lower() or "could not find" in text.lower()
    # Routes user to a recovery path.
    assert "create_trip" in text or "deleted" in text.lower()


@pytest.mark.asyncio
async def test_explain_recommendation_404_block_routes_to_get_trip(tmp_path: Path) -> None:
    """Defends against UUID hallucination at the presentation layer.
    Distinct UX from trip-not-found because the trip exists; only the
    block doesn't. Routes to get_trip to see current blocks.
    """
    token_file = _seed_token(tmp_path)
    fake = _fake_client(
        get_response=_fake_response(
            status_code=404,
            json_payload={"detail": "block not found on this trip"},
        ),
    )

    with (
        patch("trip_mcp.tools.explain_recommendation._token_file", return_value=token_file),
        patch("trip_mcp.tools.explain_recommendation._http_client", return_value=fake),
    ):
        text = await explain_recommendation(trip_id=uuid.uuid4(), block_id=uuid.uuid4())

    assert "block" in text.lower()
    assert "get_trip" in text
