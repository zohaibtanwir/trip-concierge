"""Backend ↔ agents service integration test.

Proves four things without hitting an LLM:
1. The workspace dep resolves — backend can `from trip_agents.schemas
   import AuditedPlan, TripRunRequest`.
2. The agents FastAPI app loads cleanly (no startup errors).
3. POST /run validates input via TripRunRequest (422 on invalid).
4. The patch target `trip_agents.crew.run` is correct — `mocked.called`
   is asserted. If service.py changes to `from trip_agents.crew import
   run` (binding the name into service.py's namespace) the patch would
   silently miss and the real LLM would get called. Cheap mistake,
   expensive bill. This test catches it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from trip_agents.schemas import AuditedPlan
from trip_agents.service import app


def _fake_audited_plan() -> dict[str, Any]:
    return {
        "approved": True,
        "currency": "INR",
        "total_cost": 5000.0,
        "per_day_costs": [5000.0],
        "constraints_violated": [],
        "explanation": "",
        "revision_log": ["Pass 1: nothing to revise"],
        "days": [
            {
                "day_number": 1,
                "date": "2026-07-01",
                "summary": "Test day",
                "blocks": [
                    {
                        "order": 1,
                        "type": "venue",
                        "venue_name": "Test Venue",
                        "start_time": "09:00",
                        "duration_minutes": 60,
                        "est_cost": 5000.0,
                        "currency": "INR",
                        "source_urls": ["https://example.com"],
                    }
                ],
            }
        ],
    }


def test_post_run_returns_audited_plan() -> None:
    with patch("trip_agents.crew.run", return_value=_fake_audited_plan()) as mocked:
        client = TestClient(app)
        response = client.post(
            "/run",
            json={
                "destination": "Goa, India",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
                "budget_total": 40000,
                "currency": "INR",
                "vibe": "chill",
                "group_size": 2,
                "pace": "balanced",
            },
        )
    assert response.status_code == 200, response.text
    assert mocked.called, (
        "crew.run was not invoked — patch target may be wrong (real LLM may have been called!)"
    )

    # Validates against the shared schema — proves the workspace import works.
    AuditedPlan.model_validate(response.json())


def test_post_run_rejects_missing_destination() -> None:
    """Required field missing → 422 from Pydantic, no LLM call."""
    with patch("trip_agents.crew.run") as mocked:
        client = TestClient(app)
        response = client.post("/run", json={})
    assert response.status_code == 422
    assert not mocked.called


def test_post_run_rejects_invalid_pace() -> None:
    """Literal["packed","balanced","lazy"] rejects free-form pace values."""
    with patch("trip_agents.crew.run") as mocked:
        client = TestClient(app)
        response = client.post("/run", json={"destination": "Goa", "pace": "frenetic"})
    assert response.status_code == 422
    assert not mocked.called
