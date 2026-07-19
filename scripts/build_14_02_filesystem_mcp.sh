#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"

if [[ -z "$ROOT" ]]; then
    echo "ERROR: Run this inside the odin-core Git repository."
    exit 1
fi

cd "$ROOT"

echo "Building Odin MCP repository filesystem service..."

mkdir -p odin_mcp/services
mkdir -p odin_mcp/tools

touch odin_mcp/__init__.py
touch odin_mcp/services/__init__.py
touch odin_mcp/tools/__init__.py

cat > odin_mcp/services/filesystem_service.py <<'PYFILE'
"""Safe repository filesystem operations for Odin MCP."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

_WRITE_TRUE_VALUES = {"1", "true", "yes", "on"}


class FilesystemServiceError(RuntimeError):
    """Raised when a repository filesystem operation fails."""


class RepositoryWriteDisabledError(FilesystemServiceError):
    """Raised when repository writes are disabled."""


class FilesystemService:
    """Provide filesystem access constrained to the repository root."""

    def __init__(
        self,
        repository_root: Path = REPOSITORY_ROOT,
        max_read_bytes: int = 1_000_000,
        max_write_bytes: int = 1_000_000,
        max_directory_entries: int = 1_000,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.max_read_bytes = max_read_bytes
        self.max_write_bytes = max_write_bytes
        self.max_directory_entries = max_directory_entries

        if not self.repository_root.is_dir():
            raise FilesystemServiceError(
                f"Repository root does not exist: {self.repository_root}"
            )

    @property
    def writes_enabled(self) -> bool:
        """Return whether repository filesystem writes are enabled."""

        value = os.getenv("ODIN_REPO_WRITE_ENABLED", "false")
        return value.strip().lower() in _WRITE_TRUE_VALUES

    def _require_writes_enabled(self) -> None:
        if not self.writes_enabled:
            raise RepositoryWriteDisabledError(
                "Repository writes are disabled. Set "
                "ODIN_REPO_WRITE_ENABLED=true before starting the MCP server."
            )

    def _resolve(self, path: str, *, allow_root: bool = True) -> Path:
        """Resolve a repository-relative path without allowing escape."""

        cleaned = path.strip()

        if cleaned in {"", "."}:
            if allow_root:
                return self.repository_root

            raise FilesystemServiceError("A file or directory path is required.")

        candidate = Path(cleaned)

        if candidate.is_absolute():
            raise FilesystemServiceError(
                f"Absolute paths are not allowed: {path!r}"
            )

        if ".." in candidate.parts:
            raise FilesystemServiceError(
                f"Parent traversal is not allowed: {path!r}"
            )

        resolved = (self.repository_root / candidate).resolve(strict=False)

        try:
            resolved.relative_to(self.repository_root)
        except ValueError as exc:
            raise FilesystemServiceError(
                f"Path escapes the repository: {path!r}"
            ) from exc

        return resolved

    def _relative(self, path: Path) -> str:
        relative = path.relative_to(self.repository_root).as_posix()
        return relative or "."

    def exists(self, path: str) -> dict[str, Any]:
        """Return whether a repository-relative path exists."""

        resolved = self._resolve(path)

        return {
            "path": self._relative(resolved),
            "exists": resolved.exists(),
            "is_file": resolved.is_file(),
            "is_directory": resolved.is_dir(),
        }

    def read(self, path: str) -> dict[str, Any]:
        """Read a UTF-8 text file inside the repository."""

        resolved = self._resolve(path, allow_root=False)

        if not resolved.exists():
            raise FilesystemServiceError(
                f"File does not exist: {self._relative(resolved)}"
            )

        if not resolved.is_file():
            raise FilesystemServiceError(
                f"Path is not a file: {self._relative(resolved)}"
            )

        size = resolved.stat().st_size

        if size > self.max_read_bytes:
            raise FilesystemServiceError(
                f"File exceeds the {self.max_read_bytes}-byte read limit: "
                f"{self._relative(resolved)}"
            )

        try:
            contents = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FilesystemServiceError(
                f"File is not valid UTF-8 text: {self._relative(resolved)}"
            ) from exc

        return {
            "path": self._relative(resolved),
            "size_bytes": size,
            "line_count": len(contents.splitlines()),
            "contents": contents,
        }

    def write(
        self,
        path: str,
        contents: str,
        create_parents: bool = True,
    ) -> dict[str, Any]:
        """Atomically write a UTF-8 text file inside the repository."""

        self._require_writes_enabled()

        resolved = self._resolve(path, allow_root=False)
        encoded = contents.encode("utf-8")

        if len(encoded) > self.max_write_bytes:
            raise FilesystemServiceError(
                f"Contents exceed the {self.max_write_bytes}-byte write limit."
            )

        if resolved.exists() and resolved.is_dir():
            raise FilesystemServiceError(
                f"Cannot write over a directory: {self._relative(resolved)}"
            )

        if create_parents:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        elif not resolved.parent.exists():
            raise FilesystemServiceError(
                f"Parent directory does not exist: "
                f"{self._relative(resolved.parent)}"
            )

        existed_before = resolved.exists()

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=resolved.parent,
                prefix=f".{resolved.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(contents)
                temporary_path = Path(temporary_file.name)

            temporary_path.replace(resolved)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        return {
            "path": self._relative(resolved),
            "created": not existed_before,
            "updated": existed_before,
            "size_bytes": len(encoded),
        }

    def mkdir(
        self,
        path: str,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> dict[str, Any]:
        """Create a directory inside the repository."""

        self._require_writes_enabled()

        resolved = self._resolve(path, allow_root=False)
        existed_before = resolved.exists()

        if existed_before and not resolved.is_dir():
            raise FilesystemServiceError(
                f"Path exists and is not a directory: "
                f"{self._relative(resolved)}"
            )

        resolved.mkdir(parents=parents, exist_ok=exist_ok)

        return {
            "path": self._relative(resolved),
            "created": not existed_before,
            "exists": resolved.is_dir(),
        }

    def listdir(
        self,
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 1,
    ) -> dict[str, Any]:
        """List files and directories inside the repository."""

        resolved = self._resolve(path)

        if not resolved.exists():
            raise FilesystemServiceError(
                f"Directory does not exist: {self._relative(resolved)}"
            )

        if not resolved.is_dir():
            raise FilesystemServiceError(
                f"Path is not a directory: {self._relative(resolved)}"
            )

        safe_depth = max(1, min(max_depth, 10))
        entries: list[dict[str, Any]] = []

        def visit(directory: Path, depth: int) -> None:
            if len(entries) >= self.max_directory_entries:
                return

            try:
                children = sorted(
                    directory.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except PermissionError as exc:
                raise FilesystemServiceError(
                    f"Permission denied: {self._relative(directory)}"
                ) from exc

            for child in children:
                if len(entries) >= self.max_directory_entries:
                    return

                entries.append(
                    {
                        "path": self._relative(child),
                        "name": child.name,
                        "type": (
                            "directory"
                            if child.is_dir()
                            else "file"
                            if child.is_file()
                            else "other"
                        ),
                        "size_bytes": (
                            child.stat().st_size if child.is_file() else None
                        ),
                    }
                )

                if recursive and child.is_dir() and depth < safe_depth:
                    visit(child, depth + 1)

        visit(resolved, 1)

        return {
            "path": self._relative(resolved),
            "recursive": recursive,
            "max_depth": safe_depth,
            "count": len(entries),
            "truncated": len(entries) >= self.max_directory_entries,
            "entries": entries,
        }

    def stat(self, path: str) -> dict[str, Any]:
        """Return metadata for a repository-relative path."""

        resolved = self._resolve(path)

        if not resolved.exists():
            raise FilesystemServiceError(
                f"Path does not exist: {self._relative(resolved)}"
            )

        metadata = resolved.stat()

        return {
            "path": self._relative(resolved),
            "name": resolved.name,
            "is_file": resolved.is_file(),
            "is_directory": resolved.is_dir(),
            "is_symlink": resolved.is_symlink(),
            "size_bytes": metadata.st_size,
            "modified_timestamp": metadata.st_mtime,
            "permissions": oct(metadata.st_mode & 0o777),
        }
PYFILE

cat > odin_mcp/tools/filesystem.py <<'PYFILE'
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
PYFILE

python - <<'PYFILE'
from pathlib import Path

server_path = Path("odin_mcp/server.py")
source = server_path.read_text(encoding="utf-8")

import_line = (
    "from odin_mcp.tools.filesystem import register_filesystem_tools\n"
)

if import_line not in source:
    marker = "from odin_mcp.tools.git import register_git_tools\n"

    if marker not in source:
        raise SystemExit(
            "ERROR: Could not locate Git tool import in odin_mcp/server.py"
        )

    source = source.replace(
        marker,
        marker + import_line,
        1,
    )

registration = "register_filesystem_tools(mcp)\n"

if registration not in source:
    marker = "register_git_tools(mcp)\n"

    if marker not in source:
        raise SystemExit(
            "ERROR: Could not locate Git tool registration in server.py"
        )

    source = source.replace(
        marker,
        marker + registration,
        1,
    )

server_path.write_text(source, encoding="utf-8")
PYFILE

python - <<'PYFILE'
from pathlib import Path

path = Path(".env.mcp.example")
source = path.read_text(encoding="utf-8") if path.exists() else ""

entries = {
    "ODIN_GIT_WRITE_ENABLED": "false",
    "ODIN_REPO_WRITE_ENABLED": "false",
}

lines = source.splitlines()
existing_keys = {
    line.split("=", 1)[0].strip()
    for line in lines
    if "=" in line and not line.lstrip().startswith("#")
}

if lines and lines[-1].strip():
    lines.append("")

for key, value in entries.items():
    if key not in existing_keys:
        lines.append(f"{key}={value}")

path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
PYFILE

cat > scripts/test_filesystem_mcp.py <<'PYFILE'
"""Smoke test Odin repository filesystem MCP tools."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def parse_result(response: Any) -> Any:
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


async def show(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
) -> None:
    response = await session.call_tool(name, arguments)
    result = parse_result(response)

    print(f"\n{name}\n")
    print(
        json.dumps(result, indent=2)
        if isinstance(result, (dict, list))
        else result
    )


async def main() -> None:
    async with streamable_http_client(
        "http://localhost:8000/mcp"
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            await show(session, "repo.exists", {"path": "README.md"})
            await show(
                session,
                "repo.listdir",
                {
                    "path": "odin_mcp",
                    "recursive": True,
                    "max_depth": 2,
                },
            )
            await show(
                session,
                "repo.stat",
                {"path": "odin_mcp/server.py"},
            )
            await show(
                session,
                "repo.read",
                {"path": "odin_mcp/server.py"},
            )


if __name__ == "__main__":
    asyncio.run(main())
PYFILE

python -m compileall -q \
    odin_mcp/services/filesystem_service.py \
    odin_mcp/tools/filesystem.py \
    odin_mcp/server.py \
    scripts/test_filesystem_mcp.py

echo
echo "Build 14.02 complete."
echo
echo "Created:"
echo "  odin_mcp/services/filesystem_service.py"
echo "  odin_mcp/tools/filesystem.py"
echo "  scripts/test_filesystem_mcp.py"
echo
echo "Registered tools:"
echo "  repo.exists"
echo "  repo.read"
echo "  repo.write"
echo "  repo.mkdir"
echo "  repo.listdir"
echo "  repo.stat"
echo
echo "Repository writes remain disabled unless:"
echo "  ODIN_REPO_WRITE_ENABLED=true"
