"""_extract_trip_plan failure-dump observability (slice dzc-a).

Slice dzc investigation surfaced N=1 production failure where the
crew ran for 7 minutes and `_extract_trip_plan` raised ValidationError
on `input_value={}`. No way to tell, from the error alone, whether:

  (a) the LLM literally produced `{}` as the planning_task output
  (b) CrewAI's CrewOutput rendered degenerately as "{}" despite the
      LLM producing something else
  (c) the parser path silently dropped non-`{}` content

dzc-a adds the diagnostic instrumentation needed to tell (a)/(b)/(c)
apart on the NEXT failure — without paying for a blind reproduction
($0.40 + ~9 min per attempt against a non-deterministic bug).

Two load-bearing tests:
1. Failed extraction writes the timestamped dump file with the raw
   string contents AND attaches a note pointing at the file. The
   exception type is preserved so slice-3.3's _categorize_error
   mapping still works.
2. Dump-write failure (e.g., /tmp full, /tmp missing on Windows)
   doesn't mask the original exception. Without this, a future
   refactor that removes `contextlib.suppress` would surface disk
   errors and hide the actual crew bug we're trying to diagnose.

The dump filename uses compact ISO `YYYYMMDDTHHMMSSZ` so it sorts
chronologically and is filesystem-safe (no colons or dots).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from trip_agents.crew import _extract_trip_plan


def _bad_crew_result(raw: str = "{}") -> MagicMock:
    """CrewOutput stand-in: .pydantic is None (validation failed),
    str(result) returns the raw text. This is the literal dzc-N=1
    fingerprint replayed in the test.
    """
    result = MagicMock()
    result.pydantic = None
    result.raw = raw
    result.__str__ = MagicMock(return_value=raw)
    return result


def test_extract_failure_writes_timestamped_dump_and_attaches_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dzc-a diagnostic contract:
    - A `crew_failure_<YYYYMMDDTHHMMSSZ>.json` file appears in the
      configured dump dir.
    - File contents include the raw crew_result string verbatim, so
      we can tell (a)/(b)/(c) apart on the next real failure.
    - The exception type the caller sees is preserved (not wrapped
      into a new class) so slice-3.3 _categorize_error('ValidationError')
      → "the planner produced an incomplete itinerary" still matches.
    - exc.__notes__ carries the dump path so worker.py can surface it
      into JobRun.error on a fresh line.
    """
    monkeypatch.setattr("trip_agents.crew._CREW_FAILURE_DUMP_DIR", tmp_path)

    with pytest.raises((ValueError, Exception)) as exc_info:  # noqa: PT011, BLE001
        _extract_trip_plan(_bad_crew_result(raw="{}"))

    # The exception MUST be a ValidationError or ValueError so the
    # slice-3.3 _ERROR_CATEGORIES mapping still triggers the right
    # user-facing message. Pin both class options; not Exception bare.
    exc_type_name = type(exc_info.value).__name__
    assert exc_type_name in {"ValueError", "ValidationError"}, (
        f"exception type must be preserved for slice-3.3 _categorize_error "
        f"compatibility; got {exc_type_name}"
    )

    # Exactly one dump file appears, with the timestamp pattern.
    dump_files = sorted(tmp_path.glob("crew_failure_*.json"))
    assert len(dump_files) == 1, f"expected 1 dump file, got {len(dump_files)}"
    dump = dump_files[0]
    assert re.match(r"crew_failure_\d{8}T\d{6}Z\.json$", dump.name), (
        f"filename must follow crew_failure_YYYYMMDDTHHMMSSZ.json; got {dump.name}"
    )

    # Raw content captured verbatim — this is the load-bearing
    # diagnostic. Without verbatim raw, dzc-b can't distinguish
    # (a) literal `{}` from (b) CrewOutput degeneracy.
    content = dump.read_text()
    assert "{}" in content

    # Note attached pointing at the dump file.
    notes = getattr(exc_info.value, "__notes__", None) or []
    assert any("failure dump:" in n for n in notes), (
        f"exc.__notes__ must include a 'failure dump:' line; got {notes!r}"
    )
    assert any(dump.name in n for n in notes), (
        f"the note must reference the actual dump filename; got {notes!r}"
    )


def test_extract_failure_dump_write_error_does_not_mask_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing regression-prevention test per the file-tree
    review. Without this, a future refactor that replaces
    `contextlib.suppress(OSError)` with a bare `try/except: raise`
    would surface a disk-space error and HIDE the actual crew bug.
    The whole point of dzc-a is to make crew bugs more visible, not
    less.
    """
    monkeypatch.setattr("trip_agents.crew._CREW_FAILURE_DUMP_DIR", tmp_path)

    # Patch Path.write_text on any Path under tmp_path to raise OSError.
    # Tests calling .write_text on OTHER paths (e.g., the success dump
    # at /tmp/crew_last_output.json) are unaffected because we scope
    # to a directory the helper writes to.
    original_write_text = Path.write_text

    def _raise_on_dump(self: Path, *args: Any, **kwargs: Any) -> int:
        if str(self).startswith(str(tmp_path)):
            raise OSError("no space left on device")
        return original_write_text(self, *args, **kwargs)

    with (
        patch.object(Path, "write_text", _raise_on_dump),
        pytest.raises((ValueError, Exception)) as exc_info,  # noqa: PT011, BLE001
    ):
        _extract_trip_plan(_bad_crew_result(raw="{}"))

    # Original exception still raises; disk error did NOT mask it.
    exc_type_name = type(exc_info.value).__name__
    assert exc_type_name in {"ValueError", "ValidationError"}, (
        f"original exception class must be preserved even when dump write fails; "
        f"got {exc_type_name}"
    )
    # Dump-write OSError is NOT in the traceback chain — suppressed cleanly.
    assert not isinstance(exc_info.value.__cause__, OSError)
    assert not isinstance(exc_info.value.__context__, OSError)
