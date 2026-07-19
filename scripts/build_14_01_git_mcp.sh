#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

if [[ -z "$ROOT" ]]; then
    echo "ERROR: Run this inside the odin-core Git repository."
    exit 1
fi

cd "$ROOT"

echo "Building Odin MCP Git service..."

mkdir -p odin_mcp/services
mkdir -p odin_mcp/tools
mkdir -p scripts

touch odin_mcp/__init__.py
touch odin_mcp/services/__init__.py
touch odin_mcp/tools/__init__.py

cat > odin_mcp/services/git_service.py <<'PYFILE'
"""Git operations used by Odin MCP tools."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_WRITE_TRUE_VALUES = {"1", "true", "yes", "on"}
_SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@+-]+$")


class GitServiceError(RuntimeError):
    """Raised when a Git operation fails."""


class GitWriteDisabledError(GitServiceError):
    """Raised when a write operation is attempted while writes are disabled."""


class GitService:
    """Provide controlled Git access to the Odin repository."""

    def __init__(
        self,
        repository_root: Path = REPOSITORY_ROOT,
        max_output_characters: int = 30_000,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.max_output_characters = max_output_characters

        if not (self.repository_root / ".git").exists():
            raise GitServiceError(
                f"Not a Git repository: {self.repository_root}"
            )

    @property
    def writes_enabled(self) -> bool:
        """Return whether Git write operations are enabled."""

        value = os.getenv("ODIN_GIT_WRITE_ENABLED", "false")
        return value.strip().lower() in _WRITE_TRUE_VALUES

    def _require_writes_enabled(self) -> None:
        if not self.writes_enabled:
            raise GitWriteDisabledError(
                "Git writes are disabled. Set "
                "ODIN_GIT_WRITE_ENABLED=true before starting the MCP server."
            )

    def _truncate(self, value: str) -> str:
        if len(value) <= self.max_output_characters:
            return value

        removed = len(value) - self.max_output_characters
        return (
            value[: self.max_output_characters]
            + f"\n\n[Output truncated; {removed} characters omitted.]"
        )

    def _run(
        self,
        *arguments: str,
        timeout: int = 30,
    ) -> str:
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.repository_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitServiceError(
                f"Git command timed out after {timeout} seconds."
            ) from exc

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            message = stderr or stdout or "Unknown Git error."
            raise GitServiceError(message)

        return self._truncate(stdout)

    @staticmethod
    def _validate_ref(value: str, label: str) -> str:
        value = value.strip()

        if not value:
            raise GitServiceError(f"{label} cannot be empty.")

        if value.startswith("-") or not _SAFE_REF_PATTERN.fullmatch(value):
            raise GitServiceError(f"Invalid {label}: {value!r}")

        return value

    def _validate_paths(self, paths: Sequence[str]) -> list[str]:
        if not paths:
            raise GitServiceError("At least one path is required.")

        validated: list[str] = []

        for raw_path in paths:
            candidate = Path(raw_path)

            if candidate.is_absolute() or ".." in candidate.parts:
                raise GitServiceError(
                    f"Path must remain inside the repository: {raw_path!r}"
                )

            resolved = (self.repository_root / candidate).resolve()

            try:
                resolved.relative_to(self.repository_root)
            except ValueError as exc:
                raise GitServiceError(
                    f"Path escapes the repository: {raw_path!r}"
                ) from exc

            validated.append(candidate.as_posix())

        return validated

    def branch(self) -> str:
        """Return the current branch name."""

        branch = self._run("branch", "--show-current")

        if branch:
            return branch

        return self._run("rev-parse", "--short", "HEAD")

    def status(self) -> dict[str, object]:
        """Return machine-readable repository status."""

        porcelain = self._run("status", "--short")
        files = porcelain.splitlines() if porcelain else []

        return {
            "branch": self.branch(),
            "clean": not files,
            "changed_file_count": len(files),
            "files": files,
            "writes_enabled": self.writes_enabled,
        }

    def diff(self, staged: bool = False) -> dict[str, object]:
        """Return the working-tree or staged diff."""

        arguments = ["diff"]

        if staged:
            arguments.append("--staged")

        output = self._run(*arguments)

        return {
            "staged": staged,
            "empty": not output,
            "diff": output,
        }

    def log(self, limit: int = 10) -> dict[str, object]:
        """Return recent commits."""

        safe_limit = max(1, min(limit, 50))

        output = self._run(
            "log",
            f"-{safe_limit}",
            "--date=iso-strict",
            "--pretty=format:%H%x09%an%x09%ad%x09%s",
        )

        commits: list[dict[str, str]] = []

        for line in output.splitlines():
            parts = line.split("\t", 3)

            if len(parts) != 4:
                continue

            sha, author, date, subject = parts
            commits.append(
                {
                    "sha": sha,
                    "author": author,
                    "date": date,
                    "subject": subject,
                }
            )

        return {
            "count": len(commits),
            "commits": commits,
        }

    def stage(self, paths: Sequence[str]) -> dict[str, object]:
        """Stage repository paths."""

        self._require_writes_enabled()
        validated_paths = self._validate_paths(paths)

        self._run("add", "--", *validated_paths)

        return {
            "staged": validated_paths,
            "status": self.status(),
        }

    def commit(self, message: str) -> dict[str, object]:
        """Create a commit from currently staged changes."""

        self._require_writes_enabled()

        cleaned_message = message.strip()

        if not cleaned_message:
            raise GitServiceError("Commit message cannot be empty.")

        if len(cleaned_message) > 500:
            raise GitServiceError(
                "Commit message cannot exceed 500 characters."
            )

        staged_diff = self._run("diff", "--staged", "--quiet")

        # `git diff --quiet` returns 1 when differences exist, so use
        # `git diff --staged --name-only` for a normal successful command.
        staged_files_output = self._run(
            "diff",
            "--staged",
            "--name-only",
        )
        staged_files = staged_files_output.splitlines()

        if not staged_files:
            raise GitServiceError("There are no staged changes to commit.")

        self._run("commit", "-m", cleaned_message, timeout=60)
        commit_sha = self._run("rev-parse", "HEAD")

        return {
            "commit": commit_sha,
            "message": cleaned_message,
            "files": staged_files,
        }

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> dict[str, str]:
        """Push the current branch to a configured Git remote."""

        self._require_writes_enabled()

        safe_remote = self._validate_ref(remote, "remote")
        safe_branch = self._validate_ref(
            branch or self.branch(),
            "branch",
        )

        output = self._run(
            "push",
            "--set-upstream",
            safe_remote,
            safe_branch,
            timeout=120,
        )

        return {
            "remote": safe_remote,
            "branch": safe_branch,
            "commit": self._run("rev-parse", "HEAD"),
            "output": output or "Push completed successfully.",
        }
PYFILE

cat > odin_mcp/tools/git.py <<'PYFILE'
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
PYFILE

cat > odin_mcp/server.py <<'PYFILE'
"""Odin MCP server."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
import platform
import sys


# Allow both:
#   python -m odin_mcp.server
#   python odin_mcp/server.py
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from mcp.server.fastmcp import FastMCP

from odin_mcp.tools.git import register_git_tools


mcp = FastMCP(
    "Odin",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def ping() -> str:
    """Check whether the Odin MCP server is online."""

    return "Odin MCP is online."


@mcp.tool(name="odin.info")
def odin_info() -> dict[str, object]:
    """Return information about the running Odin MCP server."""

    return {
        "name": "Odin",
        "version": "0.1.0",
        "mcp_sdk": version("mcp"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "transport": "streamable-http",
        "status": "online",
    }


register_git_tools(mcp)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
PYFILE

cat > scripts/test_mcp.py <<'PYFILE'
"""End-to-end Odin MCP smoke test."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse_result(response: Any) -> Any:
    """Extract structured or JSON text content from an MCP response."""

    if response.structuredContent is not None:
        return response.structuredContent

    if not response.content:
        return None

    text = getattr(response.content[0], "text", None)

    if text is None:
        return response.content

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def call_and_print(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> None:
    print(f"\n{tool_name}\n")

    response = await session.call_tool(
        tool_name,
        arguments or {},
    )
    result = parse_result(response)

    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    else:
        print(result)


async def main() -> None:
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("\nAvailable tools:\n")
            for tool in tools.tools:
                print(f" • {tool.name}")

            await call_and_print(session, "ping")
            await call_and_print(session, "odin.info")
            await call_and_print(session, "git.branch")
            await call_and_print(session, "git.status")
            await call_and_print(session, "git.log", {"limit": 5})


if __name__ == "__main__":
    asyncio.run(main())
PYFILE

python - <<'PYFILE'
from pathlib import Path

path = Path(".env.mcp.example")
existing = path.read_text() if path.exists() else ""

entries = {
    "MCP_HOST": "0.0.0.0",
    "MCP_PORT": "8000",
    "ODIN_GIT_WRITE_ENABLED": "false",
}

lines = existing.splitlines()
existing_keys = {
    line.split("=", 1)[0].strip()
    for line in lines
    if "=" in line and not line.lstrip().startswith("#")
}

if lines and lines[-1].strip():
    lines.append("")

lines.append("# Enable only when Odin should stage, commit, or push.")
for key, value in entries.items():
    if key not in existing_keys:
        lines.append(f"{key}={value}")

path.write_text("\n".join(lines).rstrip() + "\n")
PYFILE

python -m compileall -q odin_mcp scripts/test_mcp.py

echo
echo "Created:"
echo "  odin_mcp/services/git_service.py"
echo "  odin_mcp/tools/git.py"
echo "  odin_mcp/server.py"
echo "  scripts/test_mcp.py"
echo
echo "Git tools:"
echo "  git.branch"
echo "  git.status"
echo "  git.diff"
echo "  git.log"
echo "  git.stage"
echo "  git.commit"
echo "  git.push"
echo
echo "Build 14.01 complete."
