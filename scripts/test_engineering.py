import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import (
    streamable_http_client,
)


def parse(result):

    if result.structuredContent is not None:
        return result.structuredContent

    return json.loads(result.content[0].text)


async def call(session, tool, args):

    print(f"\n{tool}\n")

    result = await session.call_tool(
        tool,
        args,
    )

    print(
        json.dumps(
            parse(result),
            indent=2,
        )
    )


async def main():

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (
        rs,
        ws,
        _,
    ):

        async with ClientSession(
            rs,
            ws,
        ) as session:

            await session.initialize()

            await call(
                session,
                "engineering.status",
                {},
            )

            await call(
                session,
                "engineering.search_text",
                {
                    "text": "FastMCP",
                },
            )

            await call(
                session,
                "engineering.read_file",
                {
                    "path": "odin_mcp/server.py",
                },
            )

asyncio.run(main())
