#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 08 - Repository Compatibility"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run from odin-core root."
    exit 1
fi

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
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()
        self.extractor = SymbolExtractor()
        self.index = SymbolIndex()

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
        self.index.clear()

        self.load()
        self.parse()

        for file in self.files:
            tree = self.trees[file.path]

            symbols = self.extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self.index.add(symbol)

    def find_symbol(self, name: str) -> RepositorySymbol | None:
        return self.index.find(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.index.all()

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def parsed_count(self) -> int:
        return len(self.trees)

    @property
    def symbol_count(self) -> int:
        return len(self.index)
PY

echo
echo "=========================================="
echo " Step 08 Complete"
echo "=========================================="

echo
echo "Run:"
echo "cd backend"
echo "pytest tests/repository -v"