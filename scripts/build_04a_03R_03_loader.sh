#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 03 - Repository Loader"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run this from the odin-core project root."
    exit 1
fi

mkdir -p backend/app/repository

###############################################################################
# loader.py
###############################################################################

cat > backend/app/repository/loader.py <<'PY'
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
PY

echo
echo "=========================================="
echo " Step 03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_04a_03R_04_repository.sh"

echo
echo "Optional verification:"
echo "cd backend"
echo "python - <<'EOF'"
echo "from pathlib import Path"
echo "from app.repository.loader import RepositoryLoader"
echo "loader = RepositoryLoader(Path('.'))"
echo "print(f'Found {len(loader.load())} Python files')"
echo "EOF"
