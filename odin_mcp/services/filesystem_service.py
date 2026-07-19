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
