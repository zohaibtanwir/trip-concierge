"""Worker error classes for selective retry.

LLM-backed jobs are non-idempotent: every retry burns ~$0.30 of Anthropic
+ Tavily and ~9 minutes of compute. arq's default `retries=5` with
exponential backoff — sensible for stateless HTTP services where retry
costs nothing — turns into a money leak here. The worker catches errors
and re-raises one of these two:

- `RetryableJobError`: arq retries (capped at 2 in WorkerSettings).
  Reserved for transient infrastructure failures: Anthropic/Tavily 429
  or 5xx, litellm rate-limit / connection errors, transient DB hiccups
  during persist.
- `FatalJobError`: arq does NOT retry. JobRun row is written with
  status=failed and the exception message; user can re-plan explicitly
  via DELETE + POST. Reserved for: unparseable LLM output, validation
  failures, user-supplied cancellation, anything that won't get better
  on retry.

If the worker hits a bare Exception (something unexpected), it should
be treated as fatal — log it, write JobRun status=failed, surface to
the user. Don't paper over unknowns with retries.
"""

from __future__ import annotations


class WorkerError(Exception):
    """Base class — never raised directly. Catch one of the two below."""


class RetryableJobError(WorkerError):
    """Transient failure. arq will retry up to `retries=2`."""


class FatalJobError(WorkerError):
    """Permanent failure. No retry. Surfaces to the user via JobRun.error."""
