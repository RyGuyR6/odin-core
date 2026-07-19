"""End-to-end Odin MCP smoke test."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse_result(response: Any) -> Any:
    """Extract structured or JSON text content from an MCP response."""

    if response.structuredContent is not None:
        return response.structuredContent

    if not response.content:
        return None

    text = getattr(response.content[0], "text", None)

    if text is None:
        return response.content

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def call_and_print(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> None:
    print(f"\n{tool_name}\n")

    response = await session.call_tool(
        tool_name,
        arguments or {},
    )
    result = parse_result(response)

    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    else:
        print(result)


async def main() -> None:
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("\nAvailable tools:\n")
            for tool in tools.tools:
                print(f" • {tool.name}")

            await call_and_print(session, "ping")
            await call_and_print(session, "odin.info")
            await call_and_print(session, "git.branch")
            await call_and_print(session, "git.status")
            await call_and_print(session, "git.log", {"limit": 5})


if __name__ == "__main__":
    asyncio.run(main())
