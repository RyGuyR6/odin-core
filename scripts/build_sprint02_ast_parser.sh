#!/bin/bash
set -e

echo "=================================="
echo " Sprint 02 - AST Parser"
echo "=================================="

mkdir -p backend/app/repository
mkdir -p backend/tests/repository

FILES=(
backend/app/repository/parser.py
backend/app/repository/index.py
backend/app/repository/models.py
backend/app/repository/repository.py
backend/tests/repository/test_parser.py
)

for file in "${FILES[@]}"; do
    mkdir -p "$(dirname "$file")"
    touch "$file"
    echo "Created: $file"
done

echo
echo "Writing parser.py..."

cat > backend/app/repository/parser.py <<'PY'
import ast
from pathlib import Path


class RepositoryParser:

    def parse(self, file: Path) -> ast.Module:
        with open(file, "r", encoding="utf-8") as f:
            source = f.read()

        return ast.parse(source)
PY

echo "Writing index.py..."

cat > backend/app/repository/index.py <<'PY'
from dataclasses import dataclass


@dataclass(slots=True)
class Symbol:
    name: str
    kind: str
    file: str
    line: int


class SymbolIndex:

    def __init__(self):
        self.symbols = {}

    def add(self, symbol: Symbol):
        self.symbols[symbol.name] = symbol

    def find(self, name: str):
        return self.symbols.get(name)
PY

echo "Writing test..."

cat > backend/tests/repository/test_parser.py <<'PY'
from pathlib import Path

from app.repository.parser import RepositoryParser


def test_parser_returns_ast():

    parser = RepositoryParser()

    tree = parser.parse(Path(__file__))

    assert tree is not None
PY

echo
echo "Sprint 02 files generated successfully."
