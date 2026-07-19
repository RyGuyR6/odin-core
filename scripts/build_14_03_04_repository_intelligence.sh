#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python <<'PY'
from pathlib import Path

service = Path("odin_mcp/services/repository_search_service.py")

text = service.read_text()

if "def find_text(" not in text:

    text = text.rstrip()

    text += '''

    def find_text(
        self,
        text: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Alias for search().
        """
        return self.search(
            text=text,
            max_results=max_results,
        )

    def find_python(
        self,
        symbol: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Search Python source only.
        """

        return self.search(
            text=symbol,
            extensions=[".py"],
            max_results=max_results,
        )

    def file_summary(
        self,
        path: str,
    ) -> dict[str, Any]:

        file = self._resolve(path)

        if not file.exists():
            raise RepositorySearchError(
                "File not found."
            )

        contents = file.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        return {
            "path": str(file.relative_to(self.root)),
            "lines": len(contents.splitlines()),
            "characters": len(contents),
            "functions": contents.count("def "),
            "classes": contents.count("class "),
            "imports": (
                contents.count("import ")
                + contents.count("from ")
            ),
        }
'''

service.write_text(text)

print("repository_search_service.py updated")
PY

cat > odin_mcp/tools/repository_intelligence.py <<'PY'
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from odin_mcp.services.repository_search_service import (
    RepositorySearchService,
)


def register_repository_intelligence_tools(
    mcp: FastMCP,
):

    service = RepositorySearchService()

    @mcp.tool(name="repo.find_text")
    def repo_find_text(
        text: str,
        max_results: int = 100,
    ):
        return service.find_text(
            text,
            max_results=max_results,
        )

    @mcp.tool(name="repo.find_python")
    def repo_find_python(
        symbol: str,
        max_results: int = 100,
    ):
        return service.find_python(
            symbol,
            max_results=max_results,
        )

    @mcp.tool(name="repo.file_summary")
    def repo_file_summary(
        path: str,
    ):
        return service.file_summary(path)
PY

python <<'PY'
from pathlib import Path

server = Path("odin_mcp/server.py")

text = server.read_text()

IMPORT = (
    "from odin_mcp.tools.repository_intelligence "
    "import register_repository_intelligence_tools\n"
)

if IMPORT not in text:

    marker = (
        "from odin_mcp.tools.repository_search "
        "import register_repository_search_tools\n"
    )

    text = text.replace(
        marker,
        marker + IMPORT,
    )

if "register_repository_intelligence_tools(mcp)" not in text:

    marker = "register_repository_search_tools(mcp)"

    text = text.replace(
        marker,
        marker + "\nregister_repository_intelligence_tools(mcp)",
    )

server.write_text(text)

print("server.py updated")
PY

cat > scripts/test_repository_intelligence.py <<'PY'
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
PY

python -m compileall -q \
    odin_mcp \
    scripts/test_repository_intelligence.py

echo
echo "Repository intelligence installed."
