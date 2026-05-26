"""Stub maps tool — deterministic fake travel times.

Slice 2.2 uses this so Logistics can produce an itinerary with realistic-
looking travel-time fields without us paying for Google/Mapbox API calls
during dev. Slice 4.4 wires real MapLibre + a real distance API.

The output shape matches what we'll want the real tool to return so
swapping is a no-prompt-change operation later.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

Mode = Literal["walking", "driving", "transit"]
_SPEED_KMH: dict[str, int] = {"walking": 5, "driving": 30, "transit": 20}


class MapsStubInput(BaseModel):
    origin: str = Field(description="Place name, address, or venue name.")
    destination: str = Field(description="Place name, address, or venue name.")
    mode: Mode = Field(default="walking")


class MapsStubTool(BaseTool):
    name: str = "maps_travel_time"
    description: str = (
        "Estimate travel time and distance between two named places. Returns "
        "JSON with duration_minutes, distance_km, and the mode used. Useful "
        "when building a day-by-day itinerary and you need to know if two "
        "venues are too far apart to do on the same day. This is a stub: "
        "values are deterministic but not real — used while we're prototyping."
    )
    args_schema: type[BaseModel] = MapsStubInput

    def _run(self, origin: str, destination: str, mode: Mode = "walking") -> str:
        # Distance is geometry: depends only on origin+destination (not mode).
        # Stable across retries so the LLM sees a consistent answer.
        key = f"{origin.lower()}|{destination.lower()}"
        distance_km = (abs(hash(key)) % 30) + 1  # 1..30 km
        speed = _SPEED_KMH.get(mode, 5)
        duration_minutes = max(5, int(round((distance_km / speed) * 60)))
        result = {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "is_stub": True,
        }
        logger.info(
            "maps_stub.call",
            extra={"origin": origin, "destination": destination, "mode": mode},
        )
        return json.dumps(result)


maps_stub_tool = MapsStubTool()
