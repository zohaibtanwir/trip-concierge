"""Agents Service — FastAPI surface for the 4-agent crew.

Backend calls this over HTTP. Slice 2.5b adds the queue between caller
and this endpoint; today the endpoint is sync, ~9 minutes per call —
fine for dev, broken for prod (any HTTP gateway times out long before
the crew finishes). Don't deploy this without 2.5b.

Why `from trip_agents import crew` (not `from trip_agents.crew import run`):
the test in backend/tests/test_agents_service_integration.py patches
`trip_agents.crew.run`. That works because we call `crew.run(...)` —
the module-level attribute is what gets replaced. If we imported `run`
directly the patch path would have to be `trip_agents.service.run`,
which is easy to get wrong and a wrong patch silently calls the real
LLM. See slice 2.5a PR discussion.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from trip_agents import crew
from trip_agents.schemas import AuditedPlan, TripRunRequest

app = FastAPI(title="Trip Concierge Agents", version="0.1.0")


@app.post("/run", response_model=AuditedPlan)
def run(req: TripRunRequest) -> dict[str, Any]:
    """Kickoff the 4-agent crew + 2-pass audit loop. Sync, blocking, slow.

    Slice 2.5b makes this enqueue an arq job instead. Until then, the
    response time is the full crew runtime (~9 min for a 3-day trip).
    """
    return crew.run(**req.model_dump(exclude_none=True))
