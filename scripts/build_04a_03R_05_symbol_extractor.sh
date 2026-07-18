#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 05 - Symbol Extractor"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run this from the odin-core project root."
    exit 1
fi

mkdir -p backend/app/repository/extractors

###############################################################################
# symbol_extractor.py
###############################################################################

cat > backend/app/repository/extractors/symbol_extractor.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

from app.repository.models import RepositorySymbol


class SymbolExtractor(ast.NodeVisitor):
    """
    Extracts top-level classes, functions, and async functions
    from a Python AST.
    """

    def __init__(self) -> None:
        self._symbols: list[RepositorySymbol] = []
        self._module = ""
        self._file = Path()

    def extract(
        self,
        tree: ast.Module,
        *,
        module: str,
        file: Path,
    ) -> list[RepositorySymbol]:
        self._symbols.clear()
        self._module = module
        self._file = file

        self.visit(tree)

        return list(self._symbols)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbols.append(
            RepositorySymbol(
                name=node.name,
                kind="class",
                module=self._module,
                file=self._file,
                line=node.lineno,
            )
        )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbols.append(
            RepositorySymbol(
                name=node.name,
                kind="function",
                module=self._module,
                file=self._file,
                line=node.lineno,
            )
        )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._symbols.append(
            RepositorySymbol(
                name=node.name,
                kind="async_function",
                module=self._module,
                file=self._file,
                line=node.lineno,
            )
        )

        self.generic_visit(node)
PY

###############################################################################
# package init
###############################################################################

cat > backend/app/repository/extractors/__init__.py <<'PY'
from .symbol_extractor import SymbolExtractor

__all__ = [
    "SymbolExtractor",
]
PY

echo
echo "=========================================="
echo " Step 05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_04a_03R_06_tests.sh"

echo
echo "Optional verification:"
echo "cd backend"
echo "python -m compileall app/repository"