import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():

    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (
        rs,
        ws,
        _,
    ):

        async with ClientSession(rs,ws) as s:

            await s.initialize()

            r = await s.call_tool(
                "repo.replace",
                {
                    "path":"odin_mcp_write_test.txt",
                    "old":"Created",
                    "new":"Modified",
                },
            )

            print(
                json.loads(
                    r.content[0].text
                )
            )

asyncio.run(main())
