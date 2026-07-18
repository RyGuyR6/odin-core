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
echo " Odin Repository Intelligence"
echo " Sprint 06.05 - Repository Call API"
echo "=========================================="

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

marker = """    def search(self, text: str):
        return self.query.search(text)
"""

if marker not in text:
    raise SystemExit("Expected Repository.search() method not found.")

replacement = """    def search(self, text: str):
        return self.query.search(text)

    def callers(self, callee: str) -> list[str]:
        return self.query.callers(callee)

    def callees(self, caller: str) -> list[str]:
        return self.query.callees(caller)
"""

if "def callers(" not in text:
    text = text.replace(marker, replacement)

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 06.05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_06_06_tests.sh"

echo
echo "Verify:"
echo "cd backend"
echo "pytest tests/repository -v"