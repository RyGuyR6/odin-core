#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 06.03 - Repository Call Integration"
echo "=========================================="

cat > backend/app/repository/repository.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

from app.repository.extractors import (
    CallExtractor,
    ImportExtractor,
    SymbolExtractor,
)
from app.repository.graph import (
    CallGraph,
    ImportGraph,
)
from app.repository.index import SymbolIndex
from app.repository.loader import RepositoryLoader
from app.repository.models import (
    RepositoryFile,
    RepositorySymbol,
)
from app.repository.parser import RepositoryParser
from app.repository.query import RepositoryQuery


class Repository:

    def __init__(self, root: str | Path):

        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()

        self.symbol_extractor = SymbolExtractor()
        self.import_extractor = ImportExtractor()
        self.call_extractor = CallExtractor()

        self._index = SymbolIndex()
        self.index_db = self._index

        self.import_graph = ImportGraph()
        self.call_graph = CallGraph()

        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
        )

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
        self.call_graph.clear()

        for file in self.files:

            tree = self.trees[file.path]

            #
            # Symbols
            #

            symbols = self.symbol_extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self._index.add(symbol)

            #
            # Imports
            #

            imports = self.import_extractor.extract(tree)

            for imp in imports:
                self.import_graph.add(
                    file.module,
                    imp.module,
                )

            #
            # Calls
            #

            calls = self.call_extractor.extract(tree)

            for caller, callee in calls:
                self.call_graph.add(
                    caller,
                    callee,
                )

        return self._index

    def refresh(self) -> None:
        self.load()
        self.parse()
        self.index()

    #
    # Query API
    #

    def find_symbol(self, name: str) -> RepositorySymbol | None:
        return self.query.find_symbol(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.query.all_symbols()

    def dependencies(self, module: str) -> list[str]:
        return self.query.dependencies(module)

    def dependents(self, module: str) -> list[str]:
        return self.query.dependents(module)

    def search(self, text: str):
        return self.query.search(text)

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
echo " Sprint 06.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_06_04_query_calls.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"