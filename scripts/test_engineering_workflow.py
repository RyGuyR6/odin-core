import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def call(session, tool, args):
    print(f"\n=== {tool} ===")
    result = await session.call_tool(tool, args)
    print(json.dumps(parse(result), indent=2))


async def main():
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (rs, ws, _):

        async with ClientSession(rs, ws) as session:
            await session.initialize()

            await call(
                session,
                "engineering.status",
                {},
            )

            await call(
                session,
                "engineering.apply_change",
                {
                    "path": "odin_mcp_write_test.txt",
                    "old": "Modified",
                    "new": "Workflow Modified",
                    "stage": False,
                },
            )

asyncio.run(main())
