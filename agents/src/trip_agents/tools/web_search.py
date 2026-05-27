"""Tavily-backed web search tool for CrewAI agents.

Tool functions are pure-ish: typed input via Pydantic, typed output,
times out via Tavily client default (~10s), logs at start/success/failure
per .claude/rules/agent-code-style.md rule #3.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from tavily import TavilyClient  # type: ignore[import-untyped]  # no py.typed

from trip_agents.config import settings

logger = logging.getLogger(__name__)


class WebSearchInput(BaseModel):
    query: str = Field(description="Search query. Concise; the tool already adds context.")
    max_results: int = Field(default=5, ge=1, le=10)


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for travel-relevant info using Tavily. "
        "Returns up to `max_results` results, each with title, url, and a short snippet. "
        "Use this when you need fresh information about a destination, venue, opening "
        "hours, recent reviews, or anything that can change month-to-month."
    )
    args_schema: type[BaseModel] = WebSearchInput

    def _run(self, query: str, max_results: int = 5) -> str:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is not set. See backend/.env.")
        logger.info("web_search.start", extra={"query": query, "max_results": max_results})
        client = TavilyClient(api_key=settings.tavily_api_key)
        try:
            raw = client.search(query=query, max_results=max_results)
            results: list[dict[str, Any]] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in raw.get("results", [])
            ]
            logger.info("web_search.success", extra={"count": len(results)})
            return json.dumps(results)
        except Exception:
            logger.exception("web_search.failed")
            raise


web_search_tool = WebSearchTool()
