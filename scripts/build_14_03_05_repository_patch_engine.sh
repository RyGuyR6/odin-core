#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

cat > odin_mcp/services/patch_service.py <<'PY'
from __future__ import annotations

from pathlib import Path
from typing import Any

from odin_mcp.services.filesystem_service import FilesystemService


class PatchService:

    def __init__(self):
        self.fs = FilesystemService()

    def replace(
        self,
        path: str,
        old: str,
        new: str,
    ) -> dict[str, Any]:

        file = self.fs.read(path)

        contents = file["contents"]

        if old not in contents:
            raise RuntimeError(
                "Target text not found."
            )

        updated = contents.replace(old, new, 1)

        self.fs.write(
            path,
            updated,
        )

        return {
            "path": path,
            "replacements": 1,
        }

    def insert_after(
        self,
        path: str,
        anchor: str,
        text: str,
    ):

        file = self.fs.read(path)

        contents = file["contents"]

        if anchor not in contents:
            raise RuntimeError(
                "Anchor not found."
            )

        updated = contents.replace(
            anchor,
            anchor + text,
            1,
        )

        self.fs.write(
            path,
            updated,
        )

        return {
            "path": path,
            "inserted": True,
        }

    def insert_before(
        self,
        path: str,
        anchor: str,
        text: str,
    ):

        file = self.fs.read(path)

        contents = file["contents"]

        if anchor not in contents:
            raise RuntimeError(
                "Anchor not found."
            )

        updated = contents.replace(
            anchor,
            text + anchor,
            1,
        )

        self.fs.write(
            path,
            updated,
        )

        return {
            "path": path,
            "inserted": True,
        }
PY

cat > odin_mcp/tools/repository_patch.py <<'PY'
from mcp.server.fastmcp import FastMCP

from odin_mcp.services.patch_service import PatchService


def register_patch_tools(
    mcp: FastMCP,
):

    patch = PatchService()

    @mcp.tool(name="repo.replace")
    def repo_replace(
        path: str,
        old: str,
        new: str,
    ):
        return patch.replace(
            path,
            old,
            new,
        )

    @mcp.tool(name="repo.insert_after")
    def repo_insert_after(
        path: str,
        anchor: str,
        text: str,
    ):
        return patch.insert_after(
            path,
            anchor,
            text,
        )

    @mcp.tool(name="repo.insert_before")
    def repo_insert_before(
        path: str,
        anchor: str,
        text: str,
    ):
        return patch.insert_before(
            path,
            anchor,
            text,
        )
PY

python <<'PY'
from pathlib import Path

server = Path("odin_mcp/server.py")

text = server.read_text()

IMPORT = (
"from odin_mcp.tools.repository_patch "
"import register_patch_tools\n"
)

if IMPORT not in text:

    marker = (
"from odin_mcp.tools.repository_intelligence "
"import register_repository_intelligence_tools\n"
    )

    text = text.replace(
        marker,
        marker + IMPORT,
    )

if "register_patch_tools(mcp)" not in text:

    marker = (
"register_repository_intelligence_tools(mcp)"
    )

    text = text.replace(
        marker,
        marker +
"\nregister_patch_tools(mcp)"
    )

server.write_text(text)
PY

cat > scripts/test_patch_engine.py <<'PY'
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
PY

python -m compileall -q odin_mcp

echo
echo "Patch engine installed."
