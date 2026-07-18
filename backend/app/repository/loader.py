from __future__ import annotations

from pathlib import Path

from app.repository.models import RepositoryFile


class RepositoryLoader:
    """
    Discovers Python source files inside a repository.
    """

    DEFAULT_EXCLUDES = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
    }

    def __init__(self, root: Path):
        self.root = root.resolve()

    def load(self) -> list[RepositoryFile]:
        files: list[RepositoryFile] = []

        for path in sorted(self.root.rglob("*.py")):
            if self._is_excluded(path):
                continue

            relative = path.relative_to(self.root)

            module = ".".join(relative.with_suffix("").parts)

            files.append(
                RepositoryFile(
                    path=path,
                    module=module,
                )
            )

        return files

    def _is_excluded(self, path: Path) -> bool:
        return any(part in self.DEFAULT_EXCLUDES for part in path.parts)
