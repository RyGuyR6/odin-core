import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse(r):
    if r.structuredContent is not None:
        return r.structuredContent
    return json.loads(r.content[0].text)


async def call(session,name,args):
    print(f"\n{name}\n")
    r=await session.call_tool(name,args)
    print(json.dumps(parse(r),indent=2))


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

            await call(
                s,
                "repo.find_python",
                {
                    "symbol":"FastMCP"
                },
            )

            await call(
                s,
                "repo.file_summary",
                {
                    "path":"odin_mcp/server.py"
                },
            )


asyncio.run(main())
