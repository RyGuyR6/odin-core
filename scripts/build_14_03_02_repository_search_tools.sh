#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

cd "$ROOT"

mkdir -p odin_mcp/tools

cat > odin_mcp/tools/repository_search.py <<'PY'
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from odin_mcp.services.repository_search_service import (
    RepositorySearchService,
)


def register_repository_search_tools(
    mcp: FastMCP,
) -> None:

    service = RepositorySearchService()

    @mcp.tool(name="repo.tree")
    def repo_tree(
        path: str = ".",
        max_depth: int = 3,
    ) -> dict:
        """
        Return a repository tree.
        """
        return service.tree(
            path=path,
            max_depth=max_depth,
        )

    @mcp.tool(name="repo.search")
    def repo_search(
        text: str,
        extensions: list[str] | None = None,
        max_results: int = 200,
    ) -> dict:
        """
        Search repository text.
        """
        return service.search(
            text=text,
            extensions=extensions,
            max_results=max_results,
        )
PY

python -m compileall -q odin_mcp/tools/repository_search.py

echo
echo "Repository search MCP tools created."
