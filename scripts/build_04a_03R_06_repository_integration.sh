#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 06 - Repository Integration"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run from odin-core root."
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

from app.repository.extractors import SymbolExtractor
from app.repository.index import SymbolIndex
from app.repository.loader import RepositoryLoader
from app.repository.models import RepositoryFile, RepositorySymbol
from app.repository.parser import RepositoryParser


class Repository:
    """
    Repository intelligence pipeline.

        Files
          ↓
        Parser
          ↓
         AST
          ↓
    SymbolExtractor
          ↓
      SymbolIndex
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()
        self.extractor = SymbolExtractor()
        self.index = SymbolIndex()

        self.files: list[RepositoryFile] = []
        self.trees: dict[Path, ast.Module] = {}

    def refresh(self) -> None:
        self.index.clear()
        self.trees.clear()

        self.files = self.loader.load()

        for file in self.files:

            tree = self.parser.parse(file.path)

            self.trees[file.path] = tree

            symbols = self.extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self.index.add(symbol)

    def find_symbol(self, name: str) -> RepositorySymbol | None:
        return self.index.find(name)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def parsed_count(self) -> int:
        return len(self.trees)

    @property
    def symbol_count(self) -> int:
        return len(self.index)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.index.all()
PY

echo
echo "=========================================="
echo " Step 06 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/verify_repository.sh"