#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 09 - API Compatibility"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run from the odin-core project root."
    exit 1
fi

###############################################################################
# models.py
###############################################################################

cat > backend/app/repository/models.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RepositoryFile:
    path: Path
    module: str

    @property
    def extension(self) -> str:
        return self.path.suffix


@dataclass(slots=True)
class RepositoryModule:
    name: str
    file: RepositoryFile


@dataclass(slots=True)
class RepositorySymbol:
    name: str
    kind: str
    module: str
    file: Path | str
    line: int

    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportSymbol:
    module: str
    name: str | None = None
    alias: str | None = None
    line: int = 0


@dataclass(slots=True)
class RepositorySnapshot:
    files: list[RepositoryFile] = field(default_factory=list)
    modules: list[RepositoryModule] = field(default_factory=list)
    symbols: list[RepositorySymbol] = field(default_factory=list)
    imports: list[ImportSymbol] = field(default_factory=list)
PY

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

    def __init__(self, root: str | Path):

        self.root = Path(root).resolve()

        self.loader = RepositoryLoader(self.root)
        self.parser = RepositoryParser()
        self.extractor = SymbolExtractor()

        self._index = SymbolIndex()

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

        for file in self.files:

            tree = self.trees[file.path]

            symbols = self.extractor.extract(
                tree,
                module=file.module,
                file=file.path,
            )

            for symbol in symbols:
                self._index.add(symbol)

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
echo " Step 09 Complete"
echo "=========================================="

echo
echo "Run:"
echo
echo "cd backend"
echo "pytest tests/repository -v"