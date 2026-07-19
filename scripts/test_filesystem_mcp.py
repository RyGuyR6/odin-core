"""Smoke test Odin repository filesystem MCP tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse_result(response: Any) -> Any:
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


async def show(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
) -> None:
    response = await session.call_tool(name, arguments)
    result = parse_result(response)

    print(f"\n{name}\n")
    print(
        json.dumps(result, indent=2)
        if isinstance(result, (dict, list))
        else result
    )


async def main() -> None:
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            await show(session, "repo.exists", {"path": "README.md"})
            await show(
                session,
                "repo.listdir",
                {
                    "path": "odin_mcp",
                    "recursive": True,
                    "max_depth": 2,
                },
            )
            await show(
                session,
                "repo.stat",
                {"path": "odin_mcp/server.py"},
            )
            await show(
                session,
                "repo.read",
                {"path": "odin_mcp/server.py"},
            )


if __name__ == "__main__":
    asyncio.run(main())
