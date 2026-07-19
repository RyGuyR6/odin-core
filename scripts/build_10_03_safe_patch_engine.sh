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
echo " Odin Developer Infrastructure"
echo " Sprint 10.03 - Safe Patch Engine"
echo "=========================================="

mkdir -p backend/app/devtools/generators

###############################################################################
# patch_engine.py
###############################################################################

cat > backend/app/devtools/generators/patch_engine.py <<'PY'
from __future__ import annotations

from pathlib import Path


class SafePatchEngine:
    """
    Idempotent helper for safely modifying text files.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

        if self.path.exists():
            self.text = self.path.read_text(encoding="utf-8")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.text = ""

    def prepend_once(self, snippet: str) -> None:
        if snippet not in self.text:
            self.text = snippet + self.text

    def append_once(self, snippet: str) -> None:
        if snippet not in self.text:
            if self.text and not self.text.endswith("\n"):
                self.text += "\n"
            self.text += snippet

    def replace_once(self, old: str, new: str) -> bool:
        if old not in self.text:
            return False

        self.text = self.text.replace(old, new, 1)
        return True

    def ensure_contains(self, snippet: str) -> None:
        if snippet not in self.text:
            self.append_once(snippet)

    def write(self) -> None:
        self.path.write_text(self.text, encoding="utf-8")
PY

###############################################################################
# __init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/devtools/generators/__init__.py")

text = path.read_text(encoding="utf-8")

if "SafePatchEngine" not in text:

    text = "from .patch_engine import SafePatchEngine\n" + text

    text = text.replace(
        "__all__ = [",
        '__all__ = [\n    "SafePatchEngine",'
    )

path.write_text(text, encoding="utf-8")
PY

echo
echo "=========================================="
echo " Sprint 10.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_10_04_python_module_generator.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app"