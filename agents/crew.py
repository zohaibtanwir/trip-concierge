"""Crew entrypoint.

Slice 1.3: `run()` returns fixture data — the Researcher Agent object
is wired but no LLM call happens yet.

Slice 1.4 will replace the fixture read with a real
`Crew(agents=[researcher], tasks=[research_task]).kickoff(inputs=...)`
against Anthropic Sonnet 4, with Langfuse tracing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "researcher_output.json"


def run(destination: str) -> list[dict[str, Any]]:
    # destination is intentionally unused in the stub; slice 1.4 passes it
    # to the CrewAI task as a template variable.
    _ = destination
    data: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    return data
