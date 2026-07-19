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
# models.py
###############################################################################

cat > "$INTELLIGENCE_DIR/models.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FunctionInfo:
    name: str
    qualified_name: str = ""


@dataclass(slots=True)
class ClassInfo:
    name: str
    qualified_name: str = ""
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass(slots=True)
class ModuleInfo:
    name: str
    path: str

    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)

    symbol_count: int = 0


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
"""
Semantic Repository Scanner.
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    ClassInfo,
    FunctionInfo,
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


class RepositoryScanner:

    def scan(self, repository: object) -> ProjectInventory:
        inventory = ProjectInventory()

        packages: dict[str, PackageInfo] = {}

        for module in self._iter_modules(repository):

            path = Path(str(getattr(module, "path", "")))

            package_name = self._package_name(path)

            package = packages.get(package_name)

            if package is None:
                package = PackageInfo(name=package_name)
                packages[package_name] = package
                inventory.packages.append(package)

            module_info = ModuleInfo(
                name=getattr(module, "name", path.stem),
                path=str(path),
            )

            self._populate(module, module_info)

            package.modules.append(module_info)

        return inventory

    def _populate(self, module: object, info: ModuleInfo) -> None:

        classes = getattr(module, "classes", [])

        for cls in classes:
            class_info = ClassInfo(
                name=getattr(cls, "name", ""),
                qualified_name=getattr(cls, "qualified_name", ""),
            )

            for method in getattr(cls, "methods", []):
                class_info.methods.append(
                    FunctionInfo(
                        name=getattr(method, "name", ""),
                        qualified_name=getattr(method, "qualified_name", ""),
                    )
                )

            info.classes.append(class_info)

        functions = getattr(module, "functions", [])

        for fn in functions:
            info.functions.append(
                FunctionInfo(
                    name=getattr(fn, "name", ""),
                    qualified_name=getattr(fn, "qualified_name", ""),
                )
            )

        info.symbol_count = (
            len(info.classes)
            + len(info.functions)
        )

    def _iter_modules(self, repository: object):

        modules = getattr(repository, "modules", None)

        if modules is None:
            return []

        if isinstance(modules, dict):
            return modules.values()

        return modules

    @staticmethod
    def _package_name(path: Path) -> str:
        if len(path.parts) <= 1:
            return "root"

        return ".".join(path.parts[:-1])
PY

###############################################################################
# Validation
###############################################################################

python3 -m py_compile \
    "$INTELLIGENCE_DIR/models.py" \
    "$INTELLIGENCE_DIR/scanner.py"

echo
echo "=============================================="
echo "Sprint 11.02.04 completed successfully"
echo "=============================================="