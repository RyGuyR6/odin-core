import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import (
    streamable_http_client,
)


def parse(response):

    if response.structuredContent is not None:
        return response.structuredContent

    if response.content:

        try:
            return json.loads(
                response.content[0].text
            )
        except Exception:
            return response.content[0].text

    return None


async def call(
    session,
    tool,
    args,
):

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
        read_stream,
        write_stream,
        _,
    ):

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            await call(
                session,
                "repo.tree",
                {
                    "path": ".",
                    "max_depth": 2,
                },
            )

            await call(
                session,
                "repo.search",
                {
                    "text": "FastAPI",
                },
            )


asyncio.run(main())
