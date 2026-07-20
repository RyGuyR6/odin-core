from __future__ import annotations
from typing import Any
from app.tools.base import Tool
from app.tools.models import ExecutionContext, RiskLevel, ToolDefinition
from .manager import get_repository_manager
from .models import (
    CheckoutRequest, CommitRequest, FileWriteRequest, PatchRequest,
    SearchRequest, WorkspaceCreate,
)

class RepositoryStatusTool(Tool):
    definition = ToolDefinition(
        name="repository.status", description="Read Git status for an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["git", "repository", "status"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        return get_repository_manager().status(arguments["workspace_id"]).model_dump(mode="json")

class RepositoryReadTool(Tool):
    definition = ToolDefinition(
        name="repository.read_file", description="Read a UTF-8 file from an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["repository", "filesystem", "read"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        return get_repository_manager().read_file(
            arguments["workspace_id"], arguments["path"], arguments.get("max_bytes")
        )

class RepositoryWriteTool(Tool):
    definition = ToolDefinition(
        name="repository.write_file", description="Write a UTF-8 file inside an Odin repository workspace.",
        category="repository", risk=RiskLevel.medium, requires_approval=False,
        tags=["repository", "filesystem", "write"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = FileWriteRequest.model_validate(arguments)
        return get_repository_manager().write_file(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

class RepositorySearchTool(Tool):
    definition = ToolDefinition(
        name="repository.search", description="Search text across an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["repository", "search", "index"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = SearchRequest.model_validate(arguments)
        return {"results": get_repository_manager().search(arguments["workspace_id"], request)}

class RepositoryDiffTool(Tool):
    definition = ToolDefinition(
        name="repository.diff", description="Generate a Git diff for an Odin repository workspace.",
        category="repository", risk=RiskLevel.low, requires_approval=False,
        tags=["git", "repository", "diff"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        manager = get_repository_manager()
        _, path = manager.require(arguments["workspace_id"])
        return manager.git.diff(
            path, bool(arguments.get("staged", False)), arguments.get("ref")
        ).model_dump(mode="json")

class RepositoryCommitTool(Tool):
    definition = ToolDefinition(
        name="repository.commit", description="Create a Git commit in an Odin repository workspace.",
        category="repository", risk=RiskLevel.high, requires_approval=True,
        tags=["git", "repository", "commit"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = CommitRequest.model_validate(arguments)
        return get_repository_manager().commit(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

class RepositoryPatchTool(Tool):
    definition = ToolDefinition(
        name="repository.apply_patch", description="Apply a unified patch in an Odin repository workspace.",
        category="repository", risk=RiskLevel.high, requires_approval=True,
        tags=["git", "repository", "patch"],
    )
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> Any:
        request = PatchRequest.model_validate(arguments)
        return get_repository_manager().apply_patch(
            arguments["workspace_id"], request, getattr(context, "actor_id", None)
        )

def repository_tools() -> list[Tool]:
    return [
        RepositoryStatusTool(), RepositoryReadTool(), RepositoryWriteTool(),
        RepositorySearchTool(), RepositoryDiffTool(), RepositoryCommitTool(),
        RepositoryPatchTool(),
    ]
