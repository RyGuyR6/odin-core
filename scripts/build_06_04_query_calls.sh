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
echo " Sprint 06.04 - Query Call API"
echo "=========================================="

###############################################################################
# query.py
###############################################################################

cat > backend/app/repository/query.py <<'PY'
from __future__ import annotations

from app.repository.graph import (
    CallGraph,
    ImportGraph,
)
from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol


class RepositoryQuery:

    def __init__(
        self,
        symbols: SymbolIndex,
        imports: ImportGraph,
        calls: CallGraph,
    ):
        self.symbols = symbols
        self.imports = imports
        self.calls = calls

    #
    # Symbols
    #

    def find_symbol(
        self,
        name: str,
    ) -> RepositorySymbol | None:
        return self.symbols.find(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.symbols.all()

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

    #
    # Imports
    #

    def dependencies(
        self,
        module: str,
    ) -> list[str]:
        return self.imports.dependencies(module)

    def dependents(
        self,
        module: str,
    ) -> list[str]:
        return self.imports.dependents(module)

    def modules(self) -> list[str]:
        modules: set[str] = set()

        for edge in self.imports.edges:
            modules.add(edge.source)
            modules.add(edge.target)

        return sorted(modules)

    #
    # Calls
    #

    def callers(
        self,
        callee: str,
    ) -> list[str]:
        return self.calls.callers(callee)

    def callees(
        self,
        caller: str,
    ) -> list[str]:
        return self.calls.callees(caller)
PY

###############################################################################
# repository.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

old = """        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
        )"""

new = """        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
            self.call_graph,
        )"""

if old not in text:
    raise SystemExit("Expected RepositoryQuery constructor not found.")

path.write_text(text.replace(old, new))
PY

echo
echo "=========================================="
echo " Sprint 06.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_06_05_repository_query_calls.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"