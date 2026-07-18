#!/bin/bash
set -e

echo "========================================"
echo " Sprint 03 - Symbol Index"
echo "========================================"

mkdir -p backend/app/repository
mkdir -p backend/tests/repository

FILES=(
backend/app/repository/models.py
backend/app/repository/index.py
backend/app/repository/parser.py
backend/app/repository/repository.py
backend/tests/repository/test_symbol_index.py
)

for file in "${FILES[@]}"; do
    mkdir -p "$(dirname "$file")"
    touch "$file"
done

#################################################
# models.py
#################################################

cat > backend/app/repository/models.py <<'PY'
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RepositoryFile:
    path: Path
    relative_path: str
    extension: str


@dataclass(slots=True)
class Symbol:
    name: str
    kind: str
    file: str
    line: int
PY

#################################################
# index.py
#################################################

cat > backend/app/repository/index.py <<'PY'
from app.repository.models import Symbol


class SymbolIndex:

    def __init__(self):
        self._symbols: dict[str, Symbol] = {}

    def add(self, symbol: Symbol):
        self._symbols[symbol.name] = symbol

    def find(self, name: str):
        return self._symbols.get(name)

    def all(self):
        return list(self._symbols.values())

    def __len__(self):
        return len(self._symbols)
PY

#################################################
# parser.py
#################################################

cat > backend/app/repository/parser.py <<'PY'
import ast
from pathlib import Path

from app.repository.index import SymbolIndex
from app.repository.models import Symbol


class RepositoryParser:

    def parse(self, file: Path, index: SymbolIndex):

        source = file.read_text(encoding="utf-8")

        tree = ast.parse(source)

        for node in ast.walk(tree):

            if isinstance(node, ast.ClassDef):

                index.add(
                    Symbol(
                        name=node.name,
                        kind="class",
                        file=str(file),
                        line=node.lineno,
                    )
                )

            elif isinstance(node, ast.FunctionDef):

                index.add(
                    Symbol(
                        name=node.name,
                        kind="function",
                        file=str(file),
                        line=node.lineno,
                    )
                )

            elif isinstance(node, ast.AsyncFunctionDef):

                index.add(
                    Symbol(
                        name=node.name,
                        kind="async_function",
                        file=str(file),
                        line=node.lineno,
                    )
                )
PY

#################################################
# repository.py
#################################################

cat > backend/app/repository/repository.py <<'PY'
from pathlib import Path

from app.repository.index import SymbolIndex
from app.repository.loader import RepositoryLoader
from app.repository.parser import RepositoryParser


class Repository:

    def __init__(self, root):

        self.root = Path(root)

        self.files = []

        self.index_db = SymbolIndex()

        self.parser = RepositoryParser()

    def load(self):

        self.files = RepositoryLoader(self.root).load()

        return self.files

    def index(self):

        for file in self.files:

            self.parser.parse(file.path, self.index_db)

    def find_symbol(self, name):

        return self.index_db.find(name)
PY

#################################################
# tests
#################################################

cat > backend/tests/repository/test_symbol_index.py <<'PY'
from app.repository import Repository


def test_symbol_index():

    repo = Repository(".")

    repo.load()

    repo.index()

    assert len(repo.index_db) > 0


def test_find_repository_symbol():

    repo = Repository(".")

    repo.load()

    repo.index()

    symbol = repo.find_symbol("Repository")

    assert symbol is not None
    assert symbol.kind == "class"
PY

echo
echo "Sprint 03 completed."
