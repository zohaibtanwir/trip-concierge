"""Trip Concierge MCP server entry point.

Registers tools with the MCP Server and exposes a stdio main(). Slice
3.3 commit 5 adds three more tools: get_trip, refine_trip, regenerate_day.

Description strings live in agents/prompts.md (canonical) — see the
per-tool module for the synced literal and a `# Source:` comment per
.claude/rules/mcp-tool-description-style.md.

Input schemas are emitted from Pydantic models in trip_agents.schemas
via model_json_schema(). One model is the source of truth for both
runtime validation (in tools/*.py) and the JSON Schema sent to Claude
Desktop (here).

Startup probe (slice 3.2 postmortem, 2026-05-28): pings backend /health
once when main() runs and logs a clearly-visible warning if unreachable.
By design (slice 3.1) mcp_server has no DB access, so it cannot detect
schema drift directly. The probe surfaces "backend is down / unhealthy"
earlier than the first tool-call failure.
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

import httpx
import mcp.types as types
from mcp.server import Server
from trip_agents.schemas import (
    CreateTripInput,
    GetTripInput,
    RefineTripInput,
    RegenerateDayInput,
)

from trip_mcp.config import backend_url
from trip_mcp.tools import create_trip as create_trip_tool
from trip_mcp.tools import get_trip as get_trip_tool
from trip_mcp.tools import refine_trip as refine_trip_tool
from trip_mcp.tools import regenerate_day as regenerate_day_tool

logger = logging.getLogger(__name__)

server: Server = Server("trip-concierge")


def _probe_backend_health() -> None:
    """One-shot probe of backend /health. Log on failure; never raise."""
    url = backend_url().rstrip("/") + "/health"
    try:
        resp = httpx.get(url, timeout=2.0)
        if resp.status_code != 200:
            msg = (
                f"trip-concierge MCP: backend /health returned {resp.status_code} "
                f"at startup. Tool calls will fail until backend is healthy. "
                f"Check uvicorn logs."
            )
            print(msg, file=sys.stderr)
            logger.warning(msg)
            return
    except httpx.HTTPError as e:
        msg = (
            f"trip-concierge MCP: backend unreachable at {url} ({type(e).__name__}). "
            f"Tool calls will fail until backend is up. Run `make backend.dev` or "
            f"equivalent."
        )
        print(msg, file=sys.stderr)
        logger.warning(msg)


# mcp.server.Server decorators are not fully annotated upstream.
@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_trip",
            description=create_trip_tool.DESCRIPTION,
            inputSchema=CreateTripInput.model_json_schema(),
        ),
        types.Tool(
            name="get_trip",
            description=get_trip_tool.DESCRIPTION,
            inputSchema=GetTripInput.model_json_schema(),
        ),
        types.Tool(
            name="refine_trip",
            description=refine_trip_tool.DESCRIPTION,
            inputSchema=RefineTripInput.model_json_schema(),
        ),
        types.Tool(
            name="regenerate_day",
            description=regenerate_day_tool.DESCRIPTION,
            inputSchema=RegenerateDayInput.model_json_schema(),
        ),
    ]


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "create_trip":
        text = await create_trip_tool.create_trip(**arguments)
        return [types.TextContent(type="text", text=text)]
    if name == "get_trip":
        text = await get_trip_tool.get_trip(trip_id=uuid.UUID(arguments["trip_id"]))
        return [types.TextContent(type="text", text=text)]
    if name == "refine_trip":
        text = await refine_trip_tool.refine_trip(
            trip_id=uuid.UUID(arguments["trip_id"]),
            refinement_description=arguments["refinement_description"],
        )
        return [types.TextContent(type="text", text=text)]
    if name == "regenerate_day":
        text = await regenerate_day_tool.regenerate_day(
            trip_id=uuid.UUID(arguments["trip_id"]),
            day_number=int(arguments["day_number"]),
            hint=arguments.get("hint"),
        )
        return [types.TextContent(type="text", text=text)]
    raise ValueError(f"unknown tool: {name}")


async def main() -> None:
    _probe_backend_health()

    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
