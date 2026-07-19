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
