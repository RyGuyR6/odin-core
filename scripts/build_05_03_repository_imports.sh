#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 05.03 - Repository Import Integration"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

###############################################################################
# repository.py
###############################################################################

cat > backend/app/repository/repository.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

from app.repository.extractors import (
    ImportExtractor,
    SymbolExtractor,
)
from app.repository.graph import ImportGraph
from app.repository.index import SymbolIndex
from app.repository.loader import RepositoryLoader
from app.repository.models import (
    RepositoryFile,
    RepositorySymbol,
)
from app.repository.parser import RepositoryParser


class Repository:

    def __init__(self, root: str | Path):

        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()

        self.symbol_extractor = SymbolExtractor()
        self.import_extractor = ImportExtractor()

        self._index = SymbolIndex()
        self.index_db = self._index

        self.import_graph = ImportGraph()

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

    def index(self) -> SymbolIndex:

        if not self.trees:
            self.parse()

        self._index.clear()
        self.import_graph.clear()

        for file in self.files:

            tree = self.trees[file.path]

            symbols = self.symbol_extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self._index.add(symbol)

            imports = self.import_extractor.extract(tree)

            for imp in imports:
                self.import_graph.add(
                    file.module,
                    imp.module,
                )

        return self._index

    def refresh(self) -> None:
        self.load()
        self.parse()
        self.index()

    def find_symbol(self, name: str) -> RepositorySymbol | None:
        return self._index.find(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self._index.all()

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def parsed_count(self) -> int:
        return len(self.trees)

    @property
    def symbol_count(self) -> int:
        return len(self._index)
PY

echo
echo "=========================================="
echo " Sprint 05.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_05_04_query_engine.sh"

echo
echo "Verify:"
echo "cd backend"
echo "pytest tests/repository -v"