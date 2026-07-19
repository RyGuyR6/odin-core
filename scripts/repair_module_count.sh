#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

python3 <<'PY'
from pathlib import Path

path = Path("backend/app/intelligence/models.py")
text = path.read_text()

if "module_count" not in text:
    text += '''

    @property
    def module_count(self) -> int:
        return sum(len(package.modules) for package in self.packages)
'''
    path.write_text(text)

print("module_count property added.")
PY

python3 -m py_compile backend/app/intelligence/models.py