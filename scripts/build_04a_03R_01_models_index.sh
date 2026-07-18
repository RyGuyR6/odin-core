#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 01 - Models & Index"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run this from the odin-core project root."
    exit 1
fi

mkdir -p backend/app/repository

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


@dataclass(slots=True)
class RepositoryModule:
    name: str
    file: RepositoryFile


@dataclass(slots=True)
class RepositorySymbol:
    name: str
    kind: str
    module: str
    file: Path
    line: int


@dataclass(slots=True)
class ImportSymbol:
    module: str
    name: str | None = None
    alias: str | None = None


@dataclass(slots=True)
class RepositorySnapshot:
    files: list[RepositoryFile] = field(default_factory=list)
    modules: list[RepositoryModule] = field(default_factory=list)
    symbols: list[RepositorySymbol] = field(default_factory=list)
    imports: list[ImportSymbol] = field(default_factory=list)
PY

###############################################################################
# index.py
###############################################################################

cat > backend/app/repository/index.py <<'PY'
from __future__ import annotations

from app.repository.models import RepositorySymbol


class SymbolIndex:
    """
    Stores RepositorySymbol objects by name.
    """

    def __init__(self) -> None:
        self._symbols: dict[str, RepositorySymbol] = {}

    def add(self, symbol: RepositorySymbol) -> None:
        self._symbols[symbol.name] = symbol

    def find(self, name: str) -> RepositorySymbol | None:
        return self._symbols.get(name)

    def all(self) -> list[RepositorySymbol]:
        return list(self._symbols.values())

    def clear(self) -> None:
        self._symbols.clear()

    def __len__(self) -> int:
        return len(self._symbols)

    def __contains__(self, name: str) -> bool:
        return name in self._symbols
PY

echo
echo "=========================================="
echo " Step 01 Complete"
echo "=========================================="
echo
echo "Next:"
echo "./scripts/build_04a_03R_02_parser.sh"
echo
echo "Verification (optional):"
echo "cd backend"
echo "python -m compileall app/repository"