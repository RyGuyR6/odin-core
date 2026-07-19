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

    @mcp.tool(name="engineering.apply_change")
    def engineering_apply_change(
        path: str,
        old: str,
        new: str,
        stage: bool = False,
    ):
        """
        Replace text and optionally stage the file.
        """
        return service.apply_change(
            path=path,
            old=old,
            new=new,
            stage=stage,
        )

    @mcp.tool(name="engineering.commit_changes")
    def engineering_commit_changes(
        message: str,
    ):
        """
        Commit currently staged changes.
        """
        return service.commit_changes(
            message=message,
        )

    @mcp.tool(name="engineering.fix_file")
    def engineering_fix_file(
        path: str,
        old: str,
        new: str,
        commit_message: str,
    ):
        """
        Replace text, stage, and commit
        in one engineering workflow.
        """

        return service.fix_file(
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
        )

    @mcp.tool(name="engineering.submit_change")
    def engineering_submit_change(
        path: str,
        old: str,
        new: str,
        commit_message: str,
        remote: str = "origin",
        branch: str | None = None,
        push: bool = False,
    ):
        """
        Replace text, stage, commit,
        and optionally push.
        """

        return service.submit_change(
            path=path,
            old=old,
            new=new,
            commit_message=commit_message,
            remote=remote,
            branch=branch,
            push=push,
        )

