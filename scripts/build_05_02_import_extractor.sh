#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 05.02 - Import Extractor"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

mkdir -p backend/app/repository/extractors

###############################################################################
# extractors/import_extractor.py
###############################################################################

cat > backend/app/repository/extractors/import_extractor.py <<'PY'
from __future__ import annotations

import ast

from app.repository.models import ImportSymbol


class ImportExtractor(ast.NodeVisitor):
    """
    Extract import statements from a Python AST.
    """

    def __init__(self) -> None:
        self._imports: list[ImportSymbol] = []

    def extract(self, tree: ast.AST) -> list[ImportSymbol]:
        self._imports.clear()
        self.visit(tree)
        return list(self._imports)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._imports.append(
                ImportSymbol(
                    module=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""

        for alias in node.names:
            self._imports.append(
                ImportSymbol(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )

        self.generic_visit(node)
PY

###############################################################################
# Update extractors/__init__.py
###############################################################################

cat > backend/app/repository/extractors/__init__.py <<'PY'
from .import_extractor import ImportExtractor
from .symbol_extractor import SymbolExtractor

__all__ = [
    "ImportExtractor",
    "SymbolExtractor",
]
PY

echo
echo "=========================================="
echo " Sprint 05.02 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_05_03_import_repository.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"