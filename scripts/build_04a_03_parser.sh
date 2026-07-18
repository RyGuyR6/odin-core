#!/usr/bin/env bash

set -Eeuo pipefail

echo "========================================="
echo " Odin Sprint 04A.03"
echo " Production AST Parser"
echo "========================================="

if [[ ! -d "backend" ]]; then
    echo "ERROR: Run from odin-core root."
    exit 1
fi

mkdir -p backend/app/repository
mkdir -p backend/tests/repository

############################################################
# parser.py
############################################################

cat > backend/app/repository/parser.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path


class RepositoryParser:
    """
    Responsible ONLY for converting Python source into an AST.
    """

    def parse(self, file: Path) -> ast.Module:
        source = file.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file))
PY

############################################################
# test_parser.py
############################################################

cat > backend/tests/repository/test_parser.py <<'PY'
import ast
from pathlib import Path

from app.repository.parser import RepositoryParser


def test_parse_returns_ast():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    assert isinstance(tree, ast.Module)


def test_ast_contains_functions():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]

    assert len(functions) >= 2
PY

echo
echo "========================================="
echo " Sprint 04A.03 Complete"
echo "========================================="

echo
echo "Next:"
echo "cd backend"
echo "pytest tests/repository -v"