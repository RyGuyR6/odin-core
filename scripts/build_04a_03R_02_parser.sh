#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 02 - Parser"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run this from the odin-core project root."
    exit 1
fi

mkdir -p backend/app/repository

###############################################################################
# parser.py
###############################################################################

cat > backend/app/repository/parser.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path


class RepositoryParser:
    """
    Responsible only for parsing Python source into an AST.
    """

    def parse(self, file: Path) -> ast.Module:
        source = file.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file))

    def parse_source(self, source: str, filename: str = "<string>") -> ast.Module:
        return ast.parse(source, filename=filename)
PY

###############################################################################
# __init__.py
###############################################################################

cat > backend/app/repository/__init__.py <<'PY'
from .loader import RepositoryLoader
from .parser import RepositoryParser
from .repository import Repository
from .index import SymbolIndex

__all__ = [
    "Repository",
    "RepositoryLoader",
    "RepositoryParser",
    "SymbolIndex",
]
PY

echo
echo "=========================================="
echo " Step 02 Complete"
echo "=========================================="
echo
echo "Next:"
echo "./scripts/build_04a_03R_03_loader.sh"
echo
echo "Optional verification:"
echo "cd backend"
echo "python -c \"from app.repository.parser import RepositoryParser; print('Parser OK')\""