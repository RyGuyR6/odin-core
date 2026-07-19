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
    """
    Provides semantic queries over a ProjectInventory.
    """

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
        funcs: list[FunctionInfo] = []

        for module in self.modules():
            funcs.extend(module.functions)

            for cls in module.classes:
                funcs.extend(cls.methods)

        return funcs

    def find_package(self, name: str) -> PackageInfo | None:
        return next(
            (p for p in self.inventory.packages if p.name == name),
            None,
        )

    def find_module(self, name: str) -> ModuleInfo | None:
        return next(
            (m for m in self.modules() if m.name == name),
            None,
        )

    def find_class(self, name: str) -> ClassInfo | None:
        return next(
            (c for c in self.classes() if c.name == name),
            None,
        )

    def find_function(self, name: str) -> FunctionInfo | None:
        return next(
            (f for f in self.functions() if f.name == name),
            None,
        )

    def search(self, text: str) -> dict[str, list[str]]:
        text = text.lower()

        return {
            "packages": [
                p.name
                for p in self.inventory.packages
                if text in p.name.lower()
            ],
            "modules": [
                m.name
                for m in self.modules()
                if text in m.name.lower()
            ],
            "classes": [
                c.name
                for c in self.classes()
                if text in c.name.lower()
            ],
            "functions": [
                f.name
                for f in self.functions()
                if text in f.name.lower()
            ],
        }

    def statistics(self) -> dict[str, int]:
        return {
            "packages": len(self.inventory.packages),
            "modules": len(self.modules()),
            "classes": len(self.classes()),
            "functions": len(self.functions()),
        }
PY

###############################################################################
# __init__.py
###############################################################################

python3 <<'PY'
from pathlib import Path

path = Path("backend/app/intelligence/__init__.py")

text = path.read_text()

if "IntelligenceQueryEngine" not in text:
    text += "\nfrom .queries import IntelligenceQueryEngine\n"

if "__all__" in text and '"IntelligenceQueryEngine"' not in text:
    text = text.replace(
        "]",
        '    "IntelligenceQueryEngine",\n]'
    )

path.write_text(text)
PY

###############################################################################
# Validation
###############################################################################

python3 -m py_compile \
    "$INTELLIGENCE_DIR/queries.py"

echo
echo "========================================="
echo "Sprint 11.02.05 complete"
echo "========================================="