"""maps_stub tool: deterministic stub returns the expected shape."""

from __future__ import annotations

import json

from tools.maps_stub import maps_stub_tool


def test_returns_expected_fields() -> None:
    raw = maps_stub_tool._run(origin="Anjuna Beach", destination="Old Goa", mode="driving")
    out = json.loads(raw)
    assert out["origin"] == "Anjuna Beach"
    assert out["destination"] == "Old Goa"
    assert out["mode"] == "driving"
    assert isinstance(out["distance_km"], int) and out["distance_km"] >= 1
    assert isinstance(out["duration_minutes"], int) and out["duration_minutes"] >= 5
    assert out["is_stub"] is True


def test_deterministic_for_same_inputs() -> None:
    a = json.loads(maps_stub_tool._run(origin="A", destination="B", mode="walking"))
    b = json.loads(maps_stub_tool._run(origin="A", destination="B", mode="walking"))
    assert a == b, "stub must be deterministic so LLM retries see a stable answer"


def test_mode_affects_duration() -> None:
    walking = json.loads(maps_stub_tool._run(origin="A", destination="B", mode="walking"))
    driving = json.loads(maps_stub_tool._run(origin="A", destination="B", mode="driving"))
    # Same distance, different speed, so driving should take less time than walking.
    assert driving["distance_km"] == walking["distance_km"]
    assert driving["duration_minutes"] < walking["duration_minutes"]
