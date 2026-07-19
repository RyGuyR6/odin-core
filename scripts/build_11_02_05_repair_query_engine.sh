#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

INTELLIGENCE_DIR="backend/app/intelligence"

mkdir -p "$INTELLIGENCE_DIR"

###############################################################################
# queries.py
###############################################################################

cat > "$INTELLIGENCE_DIR/queries.py" <<'PY'
"""
Semantic query engine for ProjectInventory.
"""

from __future__ import annotations

from .models import (
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


class IntelligenceQueryEngine:
    """Query helper for ProjectInventory."""

    def __init__(self, inventory: ProjectInventory):
        self.inventory = inventory

    def packages(self) -> list[PackageInfo]:
        return self.inventory.packages

    def modules(self) -> list[ModuleInfo]:
        return [
            module
            for package in self.inventory.packages
            for module in package.modules
        ]

    def classes(self) -> list[ClassInfo]:
        return [
            cls
            for module in self.modules()
            for cls in module.classes
        ]

    def functions(self) -> list[FunctionInfo]:
        functions: list[FunctionInfo] = []

        for module in self.modules():
            functions.extend(module.functions)

            for cls in module.classes:
                functions.extend(cls.methods)

        return functions

    def statistics(self) -> dict[str, int]:
        return {
            "packages": len(self.inventory.packages),
            "modules": len(self.modules()),
            "classes": len(self.classes()),
            "functions": len(self.functions()),
        }

    def find_module(self, name: str) -> ModuleInfo | None:
        return next((m for m in self.modules() if m.name == name), None)

    def find_class(self, name: str) -> ClassInfo | None:
        return next((c for c in self.classes() if c.name == name), None)

    def find_function(self, name: str) -> FunctionInfo | None:
        return next((f for f in self.functions() if f.name == name), None)
PY

###############################################################################
# Update __init__.py
###############################################################################

python3 <<'PY'
from pathlib import Path

init_path = Path("backend/app/intelligence/__init__.py")
text = init_path.read_text()

if "IntelligenceQueryEngine" not in text:
    text = text.replace(
        "from .scanner import RepositoryScanner",
        "from .scanner import RepositoryScanner\nfrom .queries import IntelligenceQueryEngine",
    )

if '"IntelligenceQueryEngine"' not in text:
    text = text.replace(
        '"RepositoryScanner",',
        '"RepositoryScanner",\n    "IntelligenceQueryEngine",',
    )

init_path.write_text(text)
PY

###############################################################################
# Validation
###############################################################################

python3 -m py_compile "$INTELLIGENCE_DIR/queries.py"

echo
echo "Verifying Intelligence package..."

for file in \
    __init__.py \
    engine.py \
    models.py \
    scanner.py \
    queries.py
do
    if [[ ! -f "$INTELLIGENCE_DIR/$file" ]]; then
        echo "Missing: $file"
        exit 1
    fi
done

echo
echo "All Intelligence package files verified."