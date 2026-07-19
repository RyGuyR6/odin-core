#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

INTELLIGENCE_DIR="backend/app/intelligence"
TEST_DIR="backend/tests/intelligence"

mkdir -pv "$INTELLIGENCE_DIR"
mkdir -pv "$TEST_DIR"

###############################################################################
# __init__.py
###############################################################################

cat > "$INTELLIGENCE_DIR/__init__.py" <<'PY'
"""
Odin Code Intelligence.
"""

from .engine import IntelligenceEngine
from .scanner import RepositoryScanner
from .queries import IntelligenceQueryEngine

__all__ = [
    "IntelligenceEngine",
    "RepositoryScanner",
    "IntelligenceQueryEngine",
]
PY

###############################################################################
# models.py
###############################################################################

cat > "$INTELLIGENCE_DIR/models.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FunctionInfo:
    name: str


@dataclass(slots=True)
class ClassInfo:
    name: str
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass(slots=True)
class ModuleInfo:
    name: str
    path: str

    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)


@dataclass(slots=True)
class PackageInfo:
    name: str
    modules: list[ModuleInfo] = field(default_factory=list)


@dataclass(slots=True)
class ProjectInventory:
    packages: list[PackageInfo] = field(default_factory=list)

    @property
    def module_count(self) -> int:
        return sum(len(pkg.modules) for pkg in self.packages)
PY

###############################################################################
# scanner.py
###############################################################################

cat > "$INTELLIGENCE_DIR/scanner.py" <<'PY'
from __future__ import annotations

from .models import ProjectInventory


class RepositoryScanner:
    """
    Repository scanner placeholder.

    Future sprints will populate this inventory from the Repository.
    """

    def scan(self, repository: object) -> ProjectInventory:
        return ProjectInventory()
PY

###############################################################################
# engine.py
###############################################################################

cat > "$INTELLIGENCE_DIR/engine.py" <<'PY'
from __future__ import annotations

from .models import ProjectInventory
from .scanner import RepositoryScanner


class IntelligenceEngine:
    def __init__(self) -> None:
        self._scanner = RepositoryScanner()

    def build(self, repository: object) -> ProjectInventory:
        return self._scanner.scan(repository)
PY

###############################################################################
# queries.py
###############################################################################

cat > "$INTELLIGENCE_DIR/queries.py" <<'PY'
from __future__ import annotations

from .models import (
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


class IntelligenceQueryEngine:

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
        functions = []

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

    def find_module(self, name: str):
        return next((m for m in self.modules() if m.name == name), None)
PY

###############################################################################
# tests
###############################################################################

cat > "$TEST_DIR/test_models.py" <<'PY'
from app.intelligence.models import (
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


def test_defaults():
    inventory = ProjectInventory()

    assert inventory.packages == []
    assert inventory.module_count == 0


def test_package():
    pkg = PackageInfo(name="repo")
    pkg.modules.append(ModuleInfo(name="loader", path="loader.py"))

    assert len(pkg.modules) == 1
PY

cat > "$TEST_DIR/test_queries.py" <<'PY'
from app.intelligence.models import (
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)

from app.intelligence.queries import IntelligenceQueryEngine


def test_statistics():

    inventory = ProjectInventory()

    pkg = PackageInfo(name="repo")
    pkg.modules.append(ModuleInfo(name="loader", path="loader.py"))

    inventory.packages.append(pkg)

    query = IntelligenceQueryEngine(inventory)

    stats = query.statistics()

    assert stats["packages"] == 1
    assert stats["modules"] == 1


def test_find_module():

    inventory = ProjectInventory()

    pkg = PackageInfo(name="repo")
    pkg.modules.append(ModuleInfo(name="loader", path="loader.py"))

    inventory.packages.append(pkg)

    query = IntelligenceQueryEngine(inventory)

    assert query.find_module("loader") is not None
PY

###############################################################################
# validate
###############################################################################

echo
echo "========================================"
echo "Validating..."
echo "========================================"

for file in \
__init__.py \
engine.py \
models.py \
scanner.py \
queries.py
do
    test -f "$INTELLIGENCE_DIR/$file"
done

for file in \
test_models.py \
test_queries.py
do
    test -f "$TEST_DIR/$file"
done

python3 -m compileall "$INTELLIGENCE_DIR"

echo
echo "========================================"
echo "Repair completed successfully."
echo "========================================"