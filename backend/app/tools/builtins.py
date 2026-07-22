from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import sys
from contextlib import suppress
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.repositories.indexer import RepositoryIndexer
from app.services.github.provider import GitHubProvider
from app.services.repository_intelligence import (
    InventoryEntry,
    RepositoryIntelligenceService,
)

from .base import Tool
from .config import ToolSettings
from .exceptions import ToolValidationError
from .models import ExecutionContext, PermissionLevel, RiskLevel, ToolDefinition
from .sandbox import WorkspaceSandbox


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def _progress(context: ExecutionContext, event_type: str, payload: dict[str, Any]) -> None:
    callback = context.metadata.get("_progress_callback")
    if callable(callback):
        callback(event_type, payload)


def _trim_output(data: str, limit: int) -> tuple[str, bool]:
    encoded = data.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return data, False
    return encoded[:limit].decode("utf-8", errors="replace"), True


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(part.strip() for part in self.parts if part.strip())


async def _run_command(
    argv: list[str],
    cwd: Path,
    *,
    env: dict[str, str],
    output_limit: int,
    context: ExecutionContext,
    stream: bool,
) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    stdout_bytes = 0
    stderr_bytes = 0
    truncated = False

    async def drain(pipe, kind: str, bucket: list[str]) -> None:
        nonlocal stdout_bytes, stderr_bytes, truncated
        if pipe is None:
            return
        while True:
            chunk = await pipe.readline()
            if not chunk:
                break
            if kind == "stdout":
                stdout_bytes += len(chunk)
            else:
                stderr_bytes += len(chunk)
            if stdout_bytes + stderr_bytes > output_limit:
                truncated = True
                continue
            text = chunk.decode("utf-8", errors="replace")
            bucket.append(text)
            if stream:
                _progress(context, "execution.output", {"stream": kind, "chunk": text})

    try:
        await asyncio.gather(
            drain(proc.stdout, "stdout", stdout_parts),
            drain(proc.stderr, "stderr", stderr_parts),
        )
        code = await proc.wait()
    except asyncio.CancelledError:
        with suppress(ProcessLookupError):
            proc.kill()
        with suppress(Exception):
            await proc.wait()
        raise

    stdout = "".join(stdout_parts)
    stderr = "".join(stderr_parts)
    stdout, stdout_truncated = _trim_output(stdout, output_limit)
    stderr, stderr_truncated = _trim_output(stderr, output_limit)
    return {
        "exit_code": code,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": truncated or stdout_truncated or stderr_truncated,
    }


def _command_env(sandbox: WorkspaceSandbox, context: ExecutionContext, arguments: dict[str, Any]) -> dict[str, str]:
    env = {
        "PATH": os.getenv("PATH", ""),
        "HOME": str(sandbox.workspace(context.workspace_id)),
        "LANG": "C.UTF-8",
    }
    for key, value in dict(arguments.get("env", {})).items():
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", str(key)):
            env[str(key)] = str(value)
    return env


def _tool_health(tool: Tool, status: str = "healthy", detail: str | None = None) -> dict[str, Any]:
    result = {"status": status}
    if detail:
        result["detail"] = detail
    return result


class FileReadTool(Tool):
    definition = ToolDefinition(
        name="filesystem.read",
        description="Read a UTF-8 file inside the workspace.",
        category="filesystem",
        tags=["filesystem", "read"],
        parameters=_schema(
            {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1},
            },
            ["path"],
        ),
        capability_metadata={"plugin": "builtin", "mode": "read"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        path = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("path", "")), must_exist=True
        )
        if not path.is_file():
            raise ToolValidationError("Path is not a file")
        max_bytes = int(arguments.get("max_bytes", 262144))
        data = path.read_bytes()[:max_bytes]
        return {
            "path": str(path.relative_to(self.sandbox.workspace(context.workspace_id))),
            "content": data.decode("utf-8", errors="replace"),
            "bytes": len(data),
            "truncated": path.stat().st_size > len(data),
        }


class FileListTool(Tool):
    definition = ToolDefinition(
        name="filesystem.list",
        description="List files inside the workspace.",
        category="filesystem",
        tags=["filesystem", "read"],
        parameters=_schema(
            {
                "path": {"type": "string"},
                "recursive": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1},
            }
        ),
        capability_metadata={"plugin": "builtin", "mode": "read"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        path = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("path", ".")), must_exist=True
        )
        if not path.is_dir():
            raise ToolValidationError("Path is not a directory")
        recursive = bool(arguments.get("recursive", False))
        limit = min(int(arguments.get("limit", 500)), 2000)
        iterator = path.rglob("*") if recursive else path.iterdir()
        root = self.sandbox.workspace(context.workspace_id)
        items = []
        for item in iterator:
            if len(items) >= limit:
                break
            items.append(
                {
                    "path": str(item.relative_to(root)),
                    "type": "directory" if item.is_dir() else "file",
                    "bytes": item.stat().st_size if item.is_file() else None,
                }
            )
        return {"items": items, "count": len(items), "truncated": len(items) >= limit}


class FileSearchTool(Tool):
    definition = ToolDefinition(
        name="filesystem.search",
        description="Search text files in the workspace.",
        category="filesystem",
        tags=["filesystem", "search"],
        parameters=_schema(
            {
                "query": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["query"],
        ),
        capability_metadata={"plugin": "builtin", "mode": "read"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        query = str(arguments.get("query", ""))
        if not query:
            raise ToolValidationError("query is required")
        root = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("path", ".")), must_exist=True
        )
        pattern = str(arguments.get("glob", "**/*"))
        limit = min(int(arguments.get("limit", 100)), 500)
        case_sensitive = bool(arguments.get("case_sensitive", False))
        needle = query if case_sensitive else query.lower()
        results = []
        for path in root.glob(pattern):
            if len(results) >= limit:
                break
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                lines = path.read_text("utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(lines, 1):
                hay = line if case_sensitive else line.lower()
                if needle in hay:
                    results.append(
                        {
                            "path": str(
                                path.relative_to(self.sandbox.workspace(context.workspace_id))
                            ),
                            "line": lineno,
                            "text": line[:500],
                        }
                    )
                    if len(results) >= limit:
                        break
        return {"matches": results, "count": len(results), "truncated": len(results) >= limit}


class FileWriteTool(Tool):
    definition = ToolDefinition(
        name="filesystem.write",
        description="Write a UTF-8 file inside the workspace.",
        category="filesystem",
        risk=RiskLevel.medium,
        permission_level=PermissionLevel.approval_required,
        tags=["filesystem", "write"],
        parameters=_schema(
            {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            ["path", "content"],
        ),
        capability_metadata={"plugin": "builtin", "mode": "write"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        path = self.sandbox.resolve(context.workspace_id, str(arguments.get("path", "")))
        content = str(arguments.get("content", ""))
        overwrite = bool(arguments.get("overwrite", False))
        if path.exists() and not overwrite:
            raise ToolValidationError("File exists; set overwrite=true")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".odin-tmp")
        tmp.write_text(content, "utf-8")
        tmp.replace(path)
        _progress(context, "execution.progress", {"operation": "filesystem.write", "path": str(path.name)})
        return {
            "path": str(path.relative_to(self.sandbox.workspace(context.workspace_id))),
            "bytes": len(content.encode()),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        }


class FileMoveTool(Tool):
    definition = ToolDefinition(
        name="filesystem.move",
        description="Move or rename a file or directory inside the workspace.",
        category="filesystem",
        risk=RiskLevel.medium,
        permission_level=PermissionLevel.approval_required,
        tags=["filesystem", "write"],
        parameters=_schema(
            {"source": {"type": "string"}, "destination": {"type": "string"}},
            ["source", "destination"],
        ),
        capability_metadata={"plugin": "builtin", "mode": "write"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        source = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("source", "")), must_exist=True
        )
        destination = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("destination", ""))
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return {
            "source": str(source.relative_to(self.sandbox.workspace(context.workspace_id))),
            "destination": str(
                destination.relative_to(self.sandbox.workspace(context.workspace_id))
            ),
        }


class FileDeleteTool(Tool):
    definition = ToolDefinition(
        name="filesystem.delete",
        description="Delete a file or directory inside the workspace.",
        category="filesystem",
        risk=RiskLevel.high,
        permission_level=PermissionLevel.restricted,
        tags=["filesystem", "destructive"],
        parameters=_schema({"path": {"type": "string"}}, ["path"]),
        capability_metadata={"plugin": "builtin", "mode": "delete"},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        path = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("path", "")), must_exist=True
        )
        root = self.sandbox.workspace(context.workspace_id)
        if path == root:
            raise ToolValidationError("Cannot delete workspace root")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"deleted": str(path.relative_to(root))}


class TerminalExecuteTool(Tool):
    definition = ToolDefinition(
        name="terminal.execute",
        description="Run a command in the workspace and optionally stream output.",
        category="terminal",
        risk=RiskLevel.high,
        permission_level=PermissionLevel.approval_required,
        timeout_seconds=120,
        tags=["terminal", "execution"],
        parameters=_schema(
            {
                "argv": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string"},
                "env": {"type": "object"},
                "stream": {"type": "boolean"},
            },
            ["argv"],
        ),
        capability_metadata={
            "plugin": "builtin",
            "supports_streaming": True,
            "supports_cancellation": True,
        },
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        argv = arguments.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(item, str) and item for item in argv)
        ):
            raise ToolValidationError("argv must be a non-empty list of strings")
        deny = {"sudo", "su", "mount", "umount", "shutdown", "reboot", "mkfs", "dd"}
        if Path(argv[0]).name in deny:
            raise ToolValidationError("Command is denied by policy")
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        _progress(context, "execution.progress", {"operation": "terminal.execute", "argv": argv})
        result = await _run_command(
            argv,
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=bool(arguments.get("stream", False)),
        )
        return {"argv": argv, **result}


class PythonRunTool(Tool):
    definition = ToolDefinition(
        name="python.run",
        description="Run isolated Python source in the workspace.",
        category="terminal",
        risk=RiskLevel.high,
        permission_level=PermissionLevel.approval_required,
        timeout_seconds=60,
        tags=["terminal", "python"],
        parameters=_schema(
            {"source": {"type": "string"}, "cwd": {"type": "string"}},
            ["source"],
        ),
        capability_metadata={
            "plugin": "builtin",
            "supports_streaming": False,
            "supports_cancellation": True,
        },
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        source = str(arguments.get("source", ""))
        if not source:
            raise ToolValidationError("source is required")
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        return await _run_command(
            [sys.executable, "-I", "-c", source],
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )


class GitStatusTool(Tool):
    definition = ToolDefinition(
        name="git.status",
        description="Read Git status for the current workspace.",
        category="git",
        tags=["git", "status"],
        parameters=_schema({"cwd": {"type": "string"}}),
        capability_metadata={"plugin": "builtin"},
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        result = await _run_command(
            ["git", "status", "--short", "--branch"],
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )
        return {"cwd": str(cwd), **result}


class GitDiffTool(Tool):
    definition = ToolDefinition(
        name="git.diff",
        description="Read a Git diff for the current workspace.",
        category="git",
        tags=["git", "diff"],
        parameters=_schema(
            {
                "cwd": {"type": "string"},
                "staged": {"type": "boolean"},
                "ref": {"type": "string"},
            }
        ),
        capability_metadata={"plugin": "builtin"},
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        argv = ["git", "diff"]
        if bool(arguments.get("staged", False)):
            argv.append("--cached")
        if arguments.get("ref"):
            argv.append(str(arguments["ref"]))
        result = await _run_command(
            argv,
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )
        return {"cwd": str(cwd), **result}


class GitBranchTool(Tool):
    definition = ToolDefinition(
        name="git.branch",
        description="List branches in the current workspace.",
        category="git",
        tags=["git", "branch"],
        parameters=_schema({"cwd": {"type": "string"}}),
        capability_metadata={"plugin": "builtin"},
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        result = await _run_command(
            ["git", "branch", "--list"],
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )
        branches = [
            line.replace("*", "", 1).strip()
            for line in result["stdout"].splitlines()
            if line.strip()
        ]
        current = next((line[2:].strip() for line in result["stdout"].splitlines() if line.startswith("* ")), None)
        return {"branches": branches, "current": current, **result}


class GitCommitTool(Tool):
    definition = ToolDefinition(
        name="git.commit",
        description="Create a Git commit in the current workspace.",
        category="git",
        risk=RiskLevel.high,
        permission_level=PermissionLevel.approval_required,
        tags=["git", "commit"],
        parameters=_schema(
            {
                "message": {"type": "string"},
                "cwd": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            ["message"],
        ),
        capability_metadata={"plugin": "builtin"},
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        message = str(arguments.get("message", "")).strip()
        if not message:
            raise ToolValidationError("message is required")
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        paths = arguments.get("paths")
        if paths:
            add_result = await _run_command(
                ["git", "add", *[str(path) for path in paths]],
                cwd,
                env=_command_env(self.sandbox, context, arguments),
                output_limit=self.settings.max_output_bytes,
                context=context,
                stream=False,
            )
            if add_result["exit_code"] != 0:
                return add_result
        result = await _run_command(
            ["git", "commit", "-m", message],
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )
        return {"message": message, **result}


class GitCheckoutTool(Tool):
    definition = ToolDefinition(
        name="git.checkout",
        description="Checkout an existing branch or create a new branch.",
        category="git",
        risk=RiskLevel.high,
        permission_level=PermissionLevel.approval_required,
        tags=["git", "checkout"],
        parameters=_schema(
            {
                "branch": {"type": "string"},
                "cwd": {"type": "string"},
                "create": {"type": "boolean"},
            },
            ["branch"],
        ),
        capability_metadata={"plugin": "builtin"},
    )

    def __init__(self, sandbox: WorkspaceSandbox, settings: ToolSettings):
        self.sandbox = sandbox
        self.settings = settings

    async def execute(self, arguments, context):
        branch = str(arguments.get("branch", "")).strip()
        if not branch:
            raise ToolValidationError("branch is required")
        cwd = self.sandbox.resolve(
            context.workspace_id, str(arguments.get("cwd", ".")), must_exist=True
        )
        argv = ["git", "checkout"]
        if bool(arguments.get("create", False)):
            argv.append("-b")
        argv.append(branch)
        result = await _run_command(
            argv,
            cwd,
            env=_command_env(self.sandbox, context, arguments),
            output_limit=self.settings.max_output_bytes,
            context=context,
            stream=False,
        )
        return {"branch": branch, **result}


class GitHubRepositoriesTool(Tool):
    definition = ToolDefinition(
        name="github.repositories",
        description="List repositories or fetch metadata for a GitHub repository.",
        category="github",
        tags=["github", "repository"],
        parameters=_schema(
            {"owner": {"type": "string"}, "repo": {"type": "string"}}
        ),
        capability_metadata={"plugin": "builtin", "requires_network": True},
    )

    def __init__(self):
        self.provider = GitHubProvider()

    def health(self) -> dict[str, Any]:
        if not self.provider.configured:
            return _tool_health(self, "degraded", "ODIN_GITHUB_TOKEN is not configured")
        return _tool_health(self)

    async def execute(self, arguments, context):
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        if owner and repo:
            return await asyncio.to_thread(
                self.provider.repositories.repository, str(owner), str(repo)
            )
        return await asyncio.to_thread(self.provider.repositories.repositories)


class GitHubIssuesTool(Tool):
    definition = ToolDefinition(
        name="github.issues",
        description="List issues for a GitHub repository.",
        category="github",
        tags=["github", "issues"],
        parameters=_schema(
            {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "state": {"type": "string"},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["owner", "repo"],
        ),
        capability_metadata={"plugin": "builtin", "requires_network": True},
    )

    def __init__(self):
        self.provider = GitHubProvider()

    def health(self) -> dict[str, Any]:
        if not self.provider.configured:
            return _tool_health(self, "degraded", "ODIN_GITHUB_TOKEN is not configured")
        return _tool_health(self)

    async def execute(self, arguments, context):
        owner = str(arguments.get("owner", "")).strip()
        repo = str(arguments.get("repo", "")).strip()
        if not owner or not repo:
            raise ToolValidationError("owner and repo are required")
        state = str(arguments.get("state", "open"))
        per_page = min(max(int(arguments.get("per_page", 20)), 1), 100)
        return await asyncio.to_thread(
            self.provider.client.get,
            f"/repos/{owner}/{repo}/issues?state={quote_plus(state)}&per_page={per_page}",
        )


class GitHubPullRequestsTool(Tool):
    definition = ToolDefinition(
        name="github.pull_requests",
        description="List pull requests for a GitHub repository.",
        category="github",
        tags=["github", "pull_requests"],
        parameters=_schema(
            {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "state": {"type": "string"},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["owner", "repo"],
        ),
        capability_metadata={"plugin": "builtin", "requires_network": True},
    )

    def __init__(self):
        self.provider = GitHubProvider()

    def health(self) -> dict[str, Any]:
        if not self.provider.configured:
            return _tool_health(self, "degraded", "ODIN_GITHUB_TOKEN is not configured")
        return _tool_health(self)

    async def execute(self, arguments, context):
        owner = str(arguments.get("owner", "")).strip()
        repo = str(arguments.get("repo", "")).strip()
        if not owner or not repo:
            raise ToolValidationError("owner and repo are required")
        state = str(arguments.get("state", "open"))
        per_page = min(max(int(arguments.get("per_page", 20)), 1), 100)
        return await asyncio.to_thread(
            self.provider.client.get,
            f"/repos/{owner}/{repo}/pulls?state={quote_plus(state)}&per_page={per_page}",
        )


class RepositoryFileSearchTool(Tool):
    definition = ToolDefinition(
        name="repository.file_search",
        description="Search repository files inside the current workspace.",
        category="repository",
        tags=["repository", "search"],
        parameters=_schema(
            {
                "query": {"type": "string"},
                "glob": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1},
            },
            ["query"],
        ),
        capability_metadata={"plugin": "builtin", "uses_repository_intelligence": True},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox
        self.indexer = RepositoryIndexer()

    async def execute(self, arguments, context):
        root = self.sandbox.workspace(context.workspace_id)
        return {
            "results": self.indexer.search_content(
                root,
                str(arguments.get("query", "")),
                arguments.get("glob"),
                int(arguments.get("limit", 50)),
                bool(arguments.get("case_sensitive", False)),
            )
        }


class RepositorySymbolSearchTool(Tool):
    definition = ToolDefinition(
        name="repository.symbol_search",
        description="Search code symbols in the current workspace.",
        category="repository",
        tags=["repository", "symbols"],
        parameters=_schema(
            {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}},
            ["query"],
        ),
        capability_metadata={"plugin": "builtin", "uses_repository_intelligence": True},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox
        self.service = RepositoryIntelligenceService()
        self.indexer = RepositoryIndexer()

    async def execute(self, arguments, context):
        query = str(arguments.get("query", "")).strip().lower()
        if not query:
            raise ToolValidationError("query is required")
        limit = min(max(int(arguments.get("limit", 20)), 1), 100)
        root = self.sandbox.workspace(context.workspace_id)
        raw_entries = self.indexer.build(root)
        inventory = [
            InventoryEntry(
                path=entry.path,
                size=entry.size,
                kind=entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind),
                language=entry.language,
                binary=entry.binary,
            )
            for entry in raw_entries
        ]
        module_map = self.service._build_python_module_map(inventory)
        inventory_paths = {entry.path for entry in inventory}
        matches = []
        for entry in inventory:
            if entry.binary or not self.service._is_parseable(entry.path):
                continue
            try:
                text = (root / entry.path).read_text("utf-8", errors="replace")
            except OSError:
                continue
            analysis = self.service._analyze_file(entry, text, module_map, inventory_paths)
            for symbol in analysis.symbols:
                haystack = " ".join(
                    value
                    for value in (
                        symbol.name,
                        symbol.qualified_name,
                        symbol.file_path,
                        symbol.kind,
                    )
                    if value
                ).lower()
                if query in haystack:
                    matches.append(symbol.model_dump(mode="json"))
                    if len(matches) >= limit:
                        return {"symbols": matches, "count": len(matches)}
        return {"symbols": matches, "count": len(matches)}


class RepositoryDocumentationLookupTool(Tool):
    definition = ToolDefinition(
        name="repository.documentation_lookup",
        description="Search repository documentation files in the current workspace.",
        category="repository",
        tags=["repository", "documentation"],
        parameters=_schema(
            {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}}
        ),
        capability_metadata={"plugin": "builtin", "uses_repository_intelligence": True},
    )

    def __init__(self, sandbox: WorkspaceSandbox):
        self.sandbox = sandbox

    async def execute(self, arguments, context):
        root = self.sandbox.workspace(context.workspace_id)
        query = str(arguments.get("query", "")).strip().lower()
        limit = min(max(int(arguments.get("limit", 10)), 1), 50)
        docs = []
        for path in list(root.glob("*.md")) + list(root.glob("docs/**/*.md")):
            if not path.is_file():
                continue
            text = path.read_text("utf-8", errors="replace")
            if query and query not in text.lower() and query not in path.name.lower():
                continue
            excerpt = text[:1000]
            docs.append(
                {
                    "path": str(path.relative_to(root)),
                    "excerpt": excerpt,
                }
            )
            if len(docs) >= limit:
                break
        return {"documents": docs, "count": len(docs)}


class WebSearchTool(Tool):
    definition = ToolDefinition(
        name="web.search",
        description="Search the web for documentation and reference material.",
        category="web",
        tags=["web", "search"],
        timeout_seconds=30,
        max_retries=1,
        parameters=_schema(
            {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}},
            ["query"],
        ),
        capability_metadata={"plugin": "builtin", "requires_network": True},
    )

    async def execute(self, arguments, context):
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolValidationError("query is required")
        limit = min(max(int(arguments.get("limit", 5)), 1), 10)
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            response.raise_for_status()
            payload = response.json()
        results = []
        for item in payload.get("RelatedTopics", []):
            if "Topics" in item:
                for topic in item["Topics"]:
                    if "Text" in topic and "FirstURL" in topic:
                        results.append({"title": topic["Text"], "url": topic["FirstURL"]})
            elif "Text" in item and "FirstURL" in item:
                results.append({"title": item["Text"], "url": item["FirstURL"]})
            if len(results) >= limit:
                break
        if payload.get("AbstractURL") and len(results) < limit:
            results.insert(
                0,
                {
                    "title": payload.get("Heading") or query,
                    "url": payload["AbstractURL"],
                    "summary": payload.get("AbstractText", ""),
                },
            )
        return {"query": query, "results": results[:limit], "count": len(results[:limit])}


class WebFetchTool(Tool):
    definition = ToolDefinition(
        name="web.documentation",
        description="Fetch and summarize a documentation URL.",
        category="web",
        tags=["web", "documentation"],
        timeout_seconds=30,
        max_retries=1,
        parameters=_schema(
            {"url": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 100}},
            ["url"],
        ),
        capability_metadata={"plugin": "builtin", "requires_network": True},
    )

    async def execute(self, arguments, context):
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolValidationError("url is required")
        max_chars = min(max(int(arguments.get("max_chars", 4000)), 100), 20000)
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        parser = _HTMLStripper()
        parser.feed(response.text)
        text = parser.text()
        excerpt = text[:max_chars]
        return {"url": url, "content": excerpt, "truncated": len(text) > len(excerpt)}


class AliasTool(Tool):
    def __init__(self, definition: ToolDefinition, delegate: Tool):
        self.definition = definition
        self.delegate = delegate

    def tool_definition(self) -> ToolDefinition:
        return self.definition

    async def execute(self, arguments, context):
        return await self.delegate.execute(arguments, context)

    def health(self) -> dict[str, Any]:
        return self.delegate.health()


def register_builtin_tools(registry, sandbox, settings):
    tools: list[Tool] = [
        FileReadTool(sandbox),
        FileListTool(sandbox),
        FileSearchTool(sandbox),
        FileWriteTool(sandbox),
        FileMoveTool(sandbox),
        FileDeleteTool(sandbox),
        TerminalExecuteTool(sandbox, settings),
        PythonRunTool(sandbox, settings),
        GitStatusTool(sandbox, settings),
        GitDiffTool(sandbox, settings),
        GitBranchTool(sandbox, settings),
        GitCommitTool(sandbox, settings),
        GitCheckoutTool(sandbox, settings),
        GitHubRepositoriesTool(),
        GitHubIssuesTool(),
        GitHubPullRequestsTool(),
        RepositoryFileSearchTool(sandbox),
        RepositorySymbolSearchTool(sandbox),
        RepositoryDocumentationLookupTool(sandbox),
        WebSearchTool(),
        WebFetchTool(),
    ]

    aliases = [
        ("fs.read", "filesystem.read"),
        ("fs.list", "filesystem.list"),
        ("fs.search", "filesystem.search"),
        ("fs.write", "filesystem.write"),
        ("fs.move", "filesystem.move"),
        ("fs.delete", "filesystem.delete"),
        ("shell.run", "terminal.execute"),
    ]

    by_name = {tool.tool_definition().name: tool for tool in tools}
    for tool in tools:
        registry.register(tool, replace=True)
    for alias, target in aliases:
        definition = by_name[target].tool_definition().model_copy(
            update={"name": alias, "description": f"Alias for {target}."}
        )
        registry.register(AliasTool(definition, by_name[target]), replace=True)
