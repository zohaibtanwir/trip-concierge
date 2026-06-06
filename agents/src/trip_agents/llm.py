"""Centralized LLM config + Langfuse wiring.

Per .claude/rules/agent-code-style.md rule #9: no hardcoded model
strings in individual agent files. Per rules #4 + #10: every agent
run produces a trace with token usage / cost in Langfuse.

CrewAI uses litellm under the hood. Langfuse plugs into litellm via
callback registration — `litellm.success_callback = ["langfuse"]`
and the Langfuse SDK reads its credentials from env vars we expose
in agents/config.py.
"""

from __future__ import annotations

import logging
import os

from crewai import LLM
from langfuse import Langfuse

from trip_agents.config import settings

logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    """Singleton Langfuse client (v4 OpenTelemetry-based). Returns None if keys absent."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse keys not set — agent runs will not be traced.")
        return None
    # Langfuse SDK reads from env; populate so subprocess spans (CrewAI's
    # internal threading) also see the credentials.
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host
    # Slice 4d0: environment must be passed as constructor kwarg — SDK
    # v4 does NOT auto-read LANGFUSE_ENVIRONMENT from os.environ.
    # Verified empirically (see config.py comment on langfuse_environment).
    _langfuse_client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.langfuse_environment,
    )
    logger.info(
        "Langfuse initialized",
        extra={
            "host": settings.langfuse_host,
            "environment": settings.langfuse_environment,
        },
    )
    return _langfuse_client


def build_llm() -> LLM | None:
    """Construct the LLM. Returns None if no API key — keeps import-time
    safe for stub tests in CI (where there are no secrets). Live kickoff
    will fail loudly if llm is None.
    """
    if not settings.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY missing — Researcher will be constructed without an LLM. "
            "Stub paths still work; crew.run() will fail until backend/.env is populated."
        )
        return None
    get_langfuse()  # initialize the tracing client (no-op if keys absent)
    # litellm expects the anthropic/ prefix to route to Claude.
    #
    # Slice 225 — max_tokens=16000 override.
    # CrewAI 1.14.5's Anthropic provider hardcodes max_tokens=4096 as its
    # default (crewai/llms/providers/anthropic/completion.py:159). Under
    # this codebase's legacy `tool_use` path — which fires because Sonnet
    # 4.6 is NOT in CrewAI 1.14.5's NATIVE_STRUCTURED_OUTPUT_MODELS allow-
    # list (line 64-69 of the same file) — the entire TripPlan JSON must
    # fit inside one tool-input emission. 4096 sits right at the cliff
    # edge for a multi-day TripPlan, producing intermittent
    # `input_value={}` ValidationError failures (slice 225 diagnosis arc:
    # ~33% baseline success rate across 9 JobRuns under default 4096,
    # 2/2 success under 16000).
    #
    # Why max_tokens over a model swap (Sonnet 4.6 → 4.5): same one-line
    # surface, but max_tokens has a smaller revert blast radius. The
    # model pin would create a forward dependency on whichever Sonnet 4.6
    # features we'd lose. A future Sonnet 4.7 makes the model pin
    # immediately re-litigable; the max_tokens override carries forward.
    #
    # Forward-compat: when CrewAI adds Sonnet 4.6 (or later) to
    # NATIVE_STRUCTURED_OUTPUT_MODELS, the native path runs and the
    # max_tokens override doesn't conflict — becomes belt-and-suspenders.
    return LLM(
        model=f"anthropic/{settings.anthropic_model}",
        api_key=settings.anthropic_api_key,
        max_tokens=16000,
    )
