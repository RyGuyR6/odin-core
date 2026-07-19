#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/tools

cat > odin_mcp/tools/engineering.py <<'PY'
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from odin_mcp.services.engineering_service import EngineeringService


def register_engineering_tools(
    mcp: FastMCP,
) -> None:

    service = EngineeringService()

    @mcp.tool(name="engineering.status")
    def engineering_status():
        """
        Return engineering subsystem status.
        """
        return service.status()

    @mcp.tool(name="engineering.read_file")
    def engineering_read_file(
        path: str,
    ):
        """
        Read a repository file.
        """
        return service.read_file(
            path=path,
        )

    @mcp.tool(name="engineering.edit_file")
    def engineering_edit_file(
        path: str,
        contents: str,
    ):
        """
        Replace the entire contents of a repository file.
        """
        return service.edit_file(
            path=path,
            contents=contents,
        )

    @mcp.tool(name="engineering.replace_text")
    def engineering_replace_text(
        path: str,
        old: str,
        new: str,
    ):
        """
        Replace text inside a repository file.
        """
        return service.replace_text(
            path=path,
            old=old,
            new=new,
        )

    @mcp.tool(name="engineering.search_text")
    def engineering_search_text(
        text: str,
        max_results: int = 100,
    ):
        """
        Search repository text.
        """
        return service.search_text(
            text=text,
            max_results=max_results,
        )
PY

python <<'PY'
from pathlib import Path

server = Path("odin_mcp/server.py")
text = server.read_text()

IMPORT = (
    "from odin_mcp.tools.engineering "
    "import register_engineering_tools\n"
)

if IMPORT not in text:

    marker = (
        "from odin_mcp.tools.repository_patch "
        "import register_patch_tools\n"
    )

    if marker not in text:
        raise SystemExit(
            "Couldn't locate repository_patch import."
        )

    text = text.replace(
        marker,
        marker + IMPORT,
    )

if "register_engineering_tools(mcp)" not in text:

    marker = "register_patch_tools(mcp)"

    if marker not in text:
        raise SystemExit(
            "Couldn't locate register_patch_tools(mcp)."
        )

    text = text.replace(
        marker,
        marker + "\nregister_engineering_tools(mcp)",
    )

server.write_text(text)

print("server.py updated")
PY

cat > scripts/test_engineering.py <<'PY'
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
PY

python -m compileall -q \
    odin_mcp/tools/engineering.py \
    scripts/test_engineering.py

echo
echo "Engineering MCP tools installed."
