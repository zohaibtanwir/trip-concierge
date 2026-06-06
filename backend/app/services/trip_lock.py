"""Trip-lock helpers: active_job Redis key encoding/decoding (slice 4.5b commit 1).

Extracted from `routes/plan.py` per slice 4.5b's "refactor first" discipline.
Previously, these helpers lived inside the plan route module and were
imported by 5 sibling routes (alternative, constraints, refine, regenerate,
sources). Slice 4.5b adds a 6th importer (the new PATCH /trips/{id} route);
collocating helpers with the consumer that needed them most (the original
slice-2.5b POST /plan route) no longer reflects ownership.

Move semantic: the active_job Redis key is a *trip-level lock primitive*,
not a *plan-route detail*. The new home in `app.services.trip_lock` makes
that explicit.

Redis key shape (slice 3.3):
    trip:{id}:active_job  →  JSON {"job_id": "<arq-id>", "kind": "plan"|"refine"|"regen"}

Legacy values (pre-3.3) were plain arq job_ids without a kind tag. The
decoder treats those as kind='plan' for backwards-compat — graceful
degradation, not a crash, because the value's only purpose is routing
follow-up lifecycle calls and 'plan' is the right default.

This module is import-pure: it does NOT touch Redis directly. Callers
construct keys like `f"trip:{trip_id}:active_job"` and pass values
through these helpers. The TTL constant is also re-exposed here so
new callers don't re-derive it.
"""

from __future__ import annotations

import json

from app.schemas.plan import JobKind

__all__ = [
    "ACTIVE_JOB_KEY_TTL_SECONDS",
    "KIND_LABELS",
    "decode_active_value",
    "encode_active_value",
]

# Active-job Redis key TTL. Matches the worker's job_timeout so orphaned
# keys clear themselves even if the worker process crashes without writing
# a JobRun. Exposed for downstream callers that need to set TTL on the key.
ACTIVE_JOB_KEY_TTL_SECONDS = 900

# Human-readable labels for active_job kinds. Surfaced in 409 conflict
# messages so the user understands what's blocking their action ("a
# refinement job is already in progress…").
KIND_LABELS: dict[str, str] = {
    "plan": "planning",
    "refine": "refinement",
    "regen": "day regeneration",
}


def encode_active_value(*, job_id: str, kind: JobKind) -> str:
    """Build the JSON payload written to trip:{id}:active_job."""
    return json.dumps({"job_id": job_id, "kind": kind})


def decode_active_value(raw: bytes | str | None) -> tuple[str, str] | None:
    """Return (job_id, kind) from the active_job Redis value, or None
    if the key is absent.

    Tolerates legacy plain-string entries (anything written by pre-3.3
    code that didn't know about kind) by treating them as kind='plan'.
    Graceful degradation, not a crash — the value's only purpose is
    routing follow-up calls, and 'plan' is the right default for legacy.
    """
    if raw is None:
        return None
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "job_id" in obj:
            return str(obj["job_id"]), str(obj.get("kind", "plan"))
    except (json.JSONDecodeError, TypeError):
        pass
    return text, "plan"
