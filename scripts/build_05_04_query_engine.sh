#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 05.04 - Query Engine"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

mkdir -p backend/app/repository

###############################################################################
# query.py
###############################################################################

cat > backend/app/repository/query.py <<'PY'
from __future__ import annotations

from app.repository.graph import ImportGraph
from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol


class RepositoryQuery:

    def __init__(
        self,
        symbols: SymbolIndex,
        graph: ImportGraph,
    ):
        self.symbols = symbols
        self.graph = graph

    def find_symbol(
        self,
        name: str,
    ) -> RepositorySymbol | None:
        return self.symbols.find(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.symbols.all()

    def dependencies(
        self,
        module: str,
    ) -> list[str]:
        return self.graph.dependencies(module)

    def dependents(
        self,
        module: str,
    ) -> list[str]:
        return self.graph.dependents(module)

    def modules(self) -> list[str]:
        modules: set[str] = set()

        for edge in self.graph.edges:
            modules.add(edge.source)
            modules.add(edge.target)

        return sorted(modules)

    def search(
        self,
        text: str,
    ) -> list[RepositorySymbol]:

        text = text.lower()

        return [
            symbol
            for symbol in self.symbols.all()
            if text in symbol.name.lower()
        ]
PY

echo
echo "=========================================="
echo " Sprint 05.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_05_05_repository_query.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"