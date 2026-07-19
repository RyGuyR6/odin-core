"""Git MCP tool registration."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from odin_mcp.services.git_service import GitService


def register_git_tools(mcp: FastMCP) -> None:
    """Register Git tools with the Odin MCP server."""

    service = GitService()

    @mcp.tool(name="git.branch")
    def git_branch() -> dict[str, str]:
        """Return the current Git branch."""

        return {"branch": service.branch()}

    @mcp.tool(name="git.status")
    def git_status() -> dict[str, object]:
        """Return repository status and changed files."""

        return service.status()

    @mcp.tool(name="git.diff")
    def git_diff(staged: bool = False) -> dict[str, object]:
        """Return the unstaged or staged Git diff."""

        return service.diff(staged=staged)

    @mcp.tool(name="git.log")
    def git_log(limit: int = 10) -> dict[str, object]:
        """Return recent Git commits."""

        return service.log(limit=limit)

    @mcp.tool(name="git.stage")
    def git_stage(paths: list[str]) -> dict[str, object]:
        """Stage one or more repository-relative paths.

        Git writes must be enabled with ODIN_GIT_WRITE_ENABLED=true.
        """

        return service.stage(paths)

    @mcp.tool(name="git.commit")
    def git_commit(message: str) -> dict[str, object]:
        """Commit currently staged changes.

        Git writes must be enabled with ODIN_GIT_WRITE_ENABLED=true.
        """

        return service.commit(message)

    @mcp.tool(name="git.push")
    def git_push(
        remote: str = "origin",
        branch: str | None = None,
    ) -> dict[str, str]:
        """Push a branch to a configured remote.

        Git writes must be enabled with ODIN_GIT_WRITE_ENABLED=true.
        """

        return service.push(remote=remote, branch=branch)
