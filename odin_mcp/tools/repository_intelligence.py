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
