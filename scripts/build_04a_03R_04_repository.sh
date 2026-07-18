#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 04 - Repository Facade"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run this from the odin-core project root."
    exit 1
fi

mkdir -p backend/app/repository

###############################################################################
# repository.py
###############################################################################

cat > backend/app/repository/repository.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

from app.repository.loader import RepositoryLoader
from app.repository.models import RepositoryFile
from app.repository.parser import RepositoryParser


class Repository:
    """
    Coordinates repository discovery and parsing.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()

        self.files: list[RepositoryFile] = []
        self.trees: dict[Path, ast.Module] = {}

    def load(self) -> list[RepositoryFile]:
        self.files = self.loader.load()
        return self.files

    def parse(self) -> dict[Path, ast.Module]:
        if not self.files:
            self.load()

        self.trees.clear()

        for file in self.files:
            self.trees[file.path] = self.parser.parse(file.path)

        return self.trees

    def refresh(self) -> None:
        self.load()
        self.parse()

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def parsed_count(self) -> int:
        return len(self.trees)
PY

echo
echo "=========================================="
echo " Step 04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_04a_03R_05_symbol_extractor.sh"

echo
echo "Optional verification:"
echo "cd backend"
echo "python - <<'EOF'"
echo "from pathlib import Path"
echo "from app.repository.repository import Repository"
echo "repo = Repository(Path('.'))"
echo "repo.refresh()"
echo "print(f'Files: {repo.file_count}')"
echo "print(f'Parsed: {repo.parsed_count}')"
echo "EOF"