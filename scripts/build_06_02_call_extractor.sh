#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 06.02 - Call Extractor"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

mkdir -p backend/app/repository/extractors

###############################################################################
# extractors/call_extractor.py
###############################################################################

cat > backend/app/repository/extractors/call_extractor.py <<'PY'
from __future__ import annotations

import ast


class CallExtractor(ast.NodeVisitor):
    """
    Extracts function/method call relationships from an AST.

    Produces tuples of:
        (caller, callee)
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._current_scope: str | None = None

    def extract(self, tree: ast.AST) -> list[tuple[str, str]]:
        self.calls.clear()
        self._current_scope = None
        self.visit(tree)
        return list(self.calls)

    #
    # Scope tracking
    #

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self._current_scope
        self._current_scope = node.name
        self.generic_visit(node)
        self._current_scope = previous

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        previous = self._current_scope
        self._current_scope = node.name
        self.generic_visit(node)
        self._current_scope = previous

    #
    # Call extraction
    #

    def visit_Call(self, node: ast.Call) -> None:
        if self._current_scope is not None:
            callee = self._resolve_name(node.func)
            if callee:
                self.calls.append(
                    (
                        self._current_scope,
                        callee,
                    )
                )

        self.generic_visit(node)

    def _resolve_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            parts: list[str] = []

            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value

            if isinstance(node, ast.Name):
                parts.append(node.id)

            return ".".join(reversed(parts))

        return None
PY

###############################################################################
# extractors/__init__.py
###############################################################################

cat > backend/app/repository/extractors/__init__.py <<'PY'
from .call_extractor import CallExtractor
from .import_extractor import ImportExtractor
from .symbol_extractor import SymbolExtractor

__all__ = [
    "CallExtractor",
    "ImportExtractor",
    "SymbolExtractor",
]
PY

echo
echo "=========================================="
echo " Sprint 06.02 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_06_03_repository_calls.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"