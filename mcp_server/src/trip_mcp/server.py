"""Trip Concierge MCP server entry point.

Registers tools with the MCP Server and exposes a stdio main(). Slice
3.2 adds the first tool: create_trip.

Description strings live in agents/prompts.md (canonical) — see the
per-tool module for the synced literal and a `# Source:` comment per
.claude/rules/mcp-tool-description-style.md.
"""

from __future__ import annotations

from typing import Any

import mcp.types as types
from mcp.server import Server

from trip_mcp.tools import create_trip as create_trip_tool

server: Server = Server("trip-concierge")


# mcp.server.Server decorators are not fully annotated upstream.
@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_trip",
            description=create_trip_tool.DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": (
                            "Where the user wants to go — city, region, or country. Free-form."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Optional.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Optional.",
                    },
                    "group_size": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 1,
                        "description": "Number of travelers. Defaults to 1.",
                    },
                    "budget_total": {
                        "type": "number",
                        "minimum": 0,
                        "description": "Total trip budget (numeric). Optional.",
                    },
                    "currency": {
                        "type": "string",
                        "default": "USD",
                        "description": "ISO-4217 currency code. Defaults to USD.",
                    },
                    "pace": {
                        "type": "string",
                        "enum": ["packed", "balanced", "lazy"],
                        "default": "balanced",
                        "description": "Itinerary pace.",
                    },
                    "vibe": {
                        "type": "string",
                        "description": (
                            "Free-form vibe / style description (e.g., 'chill', "
                            "'adventure', 'foodie'). Optional."
                        ),
                    },
                },
                "required": ["destination"],
            },
        ),
    ]


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "create_trip":
        text = await create_trip_tool.create_trip(**arguments)
        return [types.TextContent(type="text", text=text)]
    raise ValueError(f"unknown tool: {name}")


async def main() -> None:
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
