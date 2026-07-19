#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/services

cat > odin_mcp/services/engineering_service.py <<'PY'
from __future__ import annotations

from typing import Any

from odin_mcp.services.filesystem_service import FilesystemService
from odin_mcp.services.git_service import GitService
from odin_mcp.services.patch_service import PatchService
from odin_mcp.services.repository_search_service import (
    RepositorySearchService,
)


class EngineeringService:
    """
    High-level engineering workflows for Odin.

    This service composes the lower-level filesystem,
    repository, patch, and git services into reusable
    engineering operations.
    """

    def __init__(self) -> None:
        self.fs = FilesystemService()
        self.git = GitService()
        self.patch = PatchService()
        self.search = RepositorySearchService()

    def status(self) -> dict[str, Any]:
        """Return an engineering status snapshot."""

        return {
            "git": self.git.status(),
            "repository_root": str(self.search.root),
            "filesystem_writes": self.fs.writes_enabled,
            "git_writes": self.git.writes_enabled,
        }

    def replace_text(
        self,
        *,
        path: str,
        old: str,
        new: str,
    ) -> dict[str, Any]:
        """
        Replace text in a repository file.
        """

        return self.patch.replace(
            path=path,
            old=old,
            new=new,
        )

    def edit_file(
        self,
        *,
        path: str,
        contents: str,
    ) -> dict[str, Any]:
        """
        Overwrite a repository file.
        """

        return self.fs.write(
            path=path,
            contents=contents,
        )

    def read_file(
        self,
        *,
        path: str,
    ) -> dict[str, Any]:
        """
        Read a repository file.
        """

        return self.fs.read(path)

    def search_text(
        self,
        *,
        text: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """
        Search the repository.
        """

        return self.search.search(
            text=text,
            max_results=max_results,
        )
PY

python -m compileall -q odin_mcp/services/engineering_service.py

echo
echo "Engineering service created."
