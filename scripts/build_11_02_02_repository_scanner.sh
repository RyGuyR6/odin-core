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

touch "$INTELLIGENCE_DIR/__init__.py"

###############################################################################
# scanner.py
###############################################################################

cat > "$INTELLIGENCE_DIR/scanner.py" <<'PY'
"""
Repository Intelligence Scanner.

Builds a ProjectInventory using Odin's Repository abstraction.

This scanner intentionally DOES NOT parse source files directly.
It consumes the Repository, Symbol Index, Resolution Engine,
and IR generated elsewhere.
"""

from __future__ import annotations

from typing import Iterable

from app.repository import Repository

from .models import (
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


class RepositoryScanner:
    """
    Converts Repository -> ProjectInventory.
    """

    def scan(self, repository: Repository) -> ProjectInventory:
        inventory = ProjectInventory()

        package_map: dict[str, PackageInfo] = {}

        for module in self._iter_modules(repository):

            package_name = self._package_name(module)

            package = package_map.get(package_name)

            if package is None:
                package = PackageInfo(name=package_name)
                package_map[package_name] = package
                inventory.packages.append(package)

            package.modules.append(
                ModuleInfo(
                    name=self._module_name(module),
                    path=self._module_path(module),
                )
            )

        return inventory

    def _iter_modules(self, repository: Repository) -> Iterable[object]:
        """
        Adapter layer.

        Later sprints will connect this to the repository facade
        without changing scanner logic.
        """

        if hasattr(repository, "modules"):
            return repository.modules.values()

        return []

    @staticmethod
    def _module_name(module: object) -> str:
        return getattr(module, "name", "unknown")

    @staticmethod
    def _module_path(module: object) -> str:
        path = getattr(module, "path", "")
        return str(path)

    @staticmethod
    def _package_name(module: object) -> str:
        package = getattr(module, "package", None)
        if package:
            return package
        return "root"
PY

###############################################################################
# engine.py
###############################################################################

cat > "$INTELLIGENCE_DIR/engine.py" <<'PY'
"""
High-level Intelligence Engine.
"""

from __future__ import annotations

from app.repository import Repository

from .models import ProjectInventory
from .scanner import RepositoryScanner


class IntelligenceEngine:

    def __init__(self) -> None:
        self._scanner = RepositoryScanner()

    def build(self, repository: Repository) -> ProjectInventory:
        return self._scanner.scan(repository)
PY

echo
echo "========================================"
echo "Sprint 11.02.02 complete"
echo "========================================"
echo
echo "Created:"
echo "  backend/app/intelligence/scanner.py"
echo "  backend/app/intelligence/engine.py"
echo
echo "Next:"
echo "  build_11_02_03_inventory_population.sh"