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
echo " Odin Semantic Intelligence"
echo " Sprint 07.06 - Resolution Tests"
echo "=========================================="

mkdir -p backend/tests/repository

###############################################################################
# test_resolution.py
###############################################################################

cat > backend/tests/repository/test_resolution.py <<'PY'
from pathlib import Path

from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol
from app.repository.resolution import (
    ResolutionContext,
    ResolutionEngine,
    SymbolResolver,
)


def make_symbol(name: str, module: str = "app.example") -> RepositorySymbol:
    return RepositorySymbol(
        name=name,
        module=module,
        file=Path("example.py"),
        line=1,
        kind="function",
    )


def test_symbol_resolver_resolves_by_name():
    index = SymbolIndex()
    index.add(make_symbol("load"))

    resolver = SymbolResolver(index)

    result = resolver.resolve(
        "load",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert result.resolved
    assert result.symbol is not None
    assert result.symbol.name == "load"


def test_symbol_resolver_returns_failure():
    index = SymbolIndex()

    resolver = SymbolResolver(index)

    result = resolver.resolve(
        "missing",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert not result.resolved
    assert result.symbol is None


def test_resolution_engine_delegates():
    index = SymbolIndex()
    index.add(make_symbol("parse"))

    engine = ResolutionEngine(SymbolResolver(index))

    result = engine.resolve(
        "parse",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert result.resolved
    assert result.symbol is not None
    assert result.symbol.name == "parse"
PY

echo
echo "=========================================="
echo " Sprint 07.06 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/verify_repository.sh"

echo
echo "Verify:"
echo "cd backend"
echo "pytest tests/repository -v"