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

from config import settings

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
    _langfuse_client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    logger.info("Langfuse initialized", extra={"host": settings.langfuse_host})
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
    return LLM(
        model=f"anthropic/{settings.anthropic_model}",
        api_key=settings.anthropic_api_key,
    )
