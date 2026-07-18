#!/usr/bin/env bash

set -Eeuo pipefail

echo "=========================================="
echo " Odin Repository Refactor"
echo " Step 10 - index_db Compatibility"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: Run from the odin-core project root."
    exit 1
fi

python <<'PY'
from pathlib import Path

repo_file = Path("backend/app/repository/repository.py")

text = repo_file.read_text()

old = """        self._index = SymbolIndex()

        self.files: list[RepositoryFile] = []
"""

new = """        self._index = SymbolIndex()

        # Backwards compatibility with older tests/code.
        self.index_db = self._index

        self.files: list[RepositoryFile] = []
"""

if old not in text:
    raise SystemExit("Expected text not found. repository.py may have changed.")

repo_file.write_text(text.replace(old, new))

print("repository.py updated successfully.")
PY

echo
echo "=========================================="
echo " Step 10 Complete"
echo "=========================================="

echo
echo "Run:"
echo "cd backend"
echo "pytest tests/repository -v"