"""Repository filesystem MCP tool registration."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from odin_mcp.services.filesystem_service import FilesystemService


def register_filesystem_tools(mcp: FastMCP) -> None:
    """Register safe repository filesystem tools."""

    service = FilesystemService()

    @mcp.tool(name="repo.exists")
    def repo_exists(path: str) -> dict[str, object]:
        """Check whether a path exists inside the repository."""

        return service.exists(path)

    @mcp.tool(name="repo.read")
    def repo_read(path: str) -> dict[str, object]:
        """Read a UTF-8 text file inside the repository."""

        return service.read(path)

    @mcp.tool(name="repo.write")
    def repo_write(
        path: str,
        contents: str,
        create_parents: bool = True,
    ) -> dict[str, object]:
        """Atomically write a UTF-8 file inside the repository.

        Repository writes must be enabled with
        ODIN_REPO_WRITE_ENABLED=true.
        """

        return service.write(
            path=path,
            contents=contents,
            create_parents=create_parents,
        )

    @mcp.tool(name="repo.mkdir")
    def repo_mkdir(
        path: str,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> dict[str, object]:
        """Create a directory inside the repository.

        Repository writes must be enabled with
        ODIN_REPO_WRITE_ENABLED=true.
        """

        return service.mkdir(
            path=path,
            parents=parents,
            exist_ok=exist_ok,
        )

    @mcp.tool(name="repo.listdir")
    def repo_listdir(
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 1,
    ) -> dict[str, object]:
        """List files and directories inside the repository."""

        return service.listdir(
            path=path,
            recursive=recursive,
            max_depth=max_depth,
        )

    @mcp.tool(name="repo.stat")
    def repo_stat(path: str) -> dict[str, object]:
        """Return metadata for a repository path."""

        return service.stat(path)
