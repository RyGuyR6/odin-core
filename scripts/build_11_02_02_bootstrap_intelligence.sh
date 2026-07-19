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

echo "Creating Intelligence package..."

mkdir -pv "$INTELLIGENCE_DIR"

###############################################################################
# __init__.py
###############################################################################

cat > "$INTELLIGENCE_DIR/__init__.py" <<'PY'
"""
Odin Code Intelligence.
"""

from .engine import IntelligenceEngine
from .scanner import RepositoryScanner

__all__ = [
    "IntelligenceEngine",
    "RepositoryScanner",
]
PY

###############################################################################
# models.py
###############################################################################

cat > "$INTELLIGENCE_DIR/models.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ModuleInfo:
    name: str
    path: str


@dataclass(slots=True)
class PackageInfo:
    name: str
    modules: list[ModuleInfo] = field(default_factory=list)


@dataclass(slots=True)
class ProjectInventory:
    packages: list[PackageInfo] = field(default_factory=list)
PY

###############################################################################
# scanner.py
###############################################################################

cat > "$INTELLIGENCE_DIR/scanner.py" <<'PY'
from __future__ import annotations

from .models import ProjectInventory


class RepositoryScanner:
    """
    Placeholder implementation.

    Future sprints will populate the inventory from the Repository
    abstraction.
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
# Validation
###############################################################################

echo
echo "Validating..."

for file in \
    "__init__.py" \
    "models.py" \
    "scanner.py" \
    "engine.py"
do
    if [[ ! -f "$INTELLIGENCE_DIR/$file" ]]; then
        echo "ERROR: Missing $file"
        exit 1
    fi
done

echo
echo "========================================"
echo "Sprint 11.02.02 bootstrap completed"
echo "========================================"

find "$INTELLIGENCE_DIR" -maxdepth 1 -type f | sort