#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

cd "$ROOT"

mkdir -p odin_mcp/services

cat > odin_mcp/services/repository_search_service.py <<'PY'
from __future__ import annotations

from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class RepositorySearchError(RuntimeError):
    pass


class RepositorySearchService:
    """
    Repository search utilities used by Odin MCP.
    """

    def __init__(self, root: Path = REPOSITORY_ROOT):
        self.root = root.resolve()

    def _resolve(self, path: str = ".") -> Path:
        p = (self.root / path).resolve()

        try:
            p.relative_to(self.root)
        except ValueError:
            raise RepositorySearchError(
                "Path escapes repository."
            )

        return p

    def tree(
        self,
        path: str = ".",
        max_depth: int = 3,
    ) -> dict[str, Any]:

        root = self._resolve(path)

        results: list[dict[str, Any]] = []

        def walk(directory: Path, depth: int):

            if depth > max_depth:
                return

            for child in sorted(
                directory.iterdir(),
                key=lambda x: (not x.is_dir(), x.name.lower()),
            ):

                results.append(
                    {
                        "path": str(child.relative_to(self.root)),
                        "type": (
                            "directory"
                            if child.is_dir()
                            else "file"
                        ),
                    }
                )

                if child.is_dir():
                    walk(child, depth + 1)

        walk(root, 0)

        return {
            "count": len(results),
            "entries": results,
        }

    def search(
        self,
        text: str,
        extensions: list[str] | None = None,
        max_results: int = 200,
    ) -> dict[str, Any]:

        if not text.strip():
            raise RepositorySearchError(
                "Search text cannot be empty."
            )

        if extensions is None:
            extensions = [
                ".py",
                ".md",
                ".txt",
                ".yaml",
                ".yml",
                ".json",
                ".toml",
                ".ini",
            ]

        matches = []

        for file in self.root.rglob("*"):

            if not file.is_file():
                continue

            if file.suffix not in extensions:
                continue

            try:
                lines = file.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ).splitlines()
            except Exception:
                continue

            for number, line in enumerate(lines, start=1):

                if text.lower() in line.lower():

                    matches.append(
                        {
                            "path": str(
                                file.relative_to(self.root)
                            ),
                            "line": number,
                            "text": line.strip(),
                        }
                    )

                    if len(matches) >= max_results:
                        return {
                            "query": text,
                            "count": len(matches),
                            "results": matches,
                        }

        return {
            "query": text,
            "count": len(matches),
            "results": matches,
        }
PY

python -m compileall -q odin_mcp/services/repository_search_service.py

echo
echo "Repository search service created."
