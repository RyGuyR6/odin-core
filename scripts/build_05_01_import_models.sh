#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 05.01 - Import Graph Foundation"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

mkdir -p backend/app/repository/graph

###############################################################################
# graph/import_graph.py
###############################################################################

cat > backend/app/repository/graph/import_graph.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ImportEdge:
    """
    Directed dependency from one module to another.
    """

    source: str
    target: str


@dataclass(slots=True)
class ImportGraph:
    """
    Stores repository module dependencies.
    """

    edges: list[ImportEdge] = field(default_factory=list)

    def add(self, source: str, target: str) -> None:
        self.edges.append(
            ImportEdge(
                source=source,
                target=target,
            )
        )

    def dependencies(self, module: str) -> list[str]:
        return [
            edge.target
            for edge in self.edges
            if edge.source == module
        ]

    def dependents(self, module: str) -> list[str]:
        return [
            edge.source
            for edge in self.edges
            if edge.target == module
        ]

    def clear(self) -> None:
        self.edges.clear()

    def __contains__(self, module: str) -> bool:
        return any(
            edge.source == module or edge.target == module
            for edge in self.edges
        )

    def __len__(self) -> int:
        return len(self.edges)
PY

###############################################################################
# graph/__init__.py
###############################################################################

cat > backend/app/repository/graph/__init__.py <<'PY'
from .import_graph import ImportEdge, ImportGraph

__all__ = [
    "ImportEdge",
    "ImportGraph",
]
PY

echo
echo "=========================================="
echo " Sprint 05.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_05_02_import_extractor.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"