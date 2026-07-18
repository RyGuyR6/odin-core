#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=========================================="
echo " Odin Repository Intelligence"
echo " Sprint 06.01 - Call Graph Foundation"
echo "=========================================="

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

mkdir -p backend/app/repository/graph

###############################################################################
# graph/call_graph.py
###############################################################################

cat > backend/app/repository/graph/call_graph.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CallEdge:
    """
    Represents one function or method calling another.
    """

    caller: str
    callee: str


@dataclass(slots=True)
class CallGraph:
    """
    Directed graph of function and method calls.
    """

    edges: list[CallEdge] = field(default_factory=list)

    def add(self, caller: str, callee: str) -> None:
        self.edges.append(
            CallEdge(
                caller=caller,
                callee=callee,
            )
        )

    def callees(self, caller: str) -> list[str]:
        return [
            edge.callee
            for edge in self.edges
            if edge.caller == caller
        ]

    def callers(self, callee: str) -> list[str]:
        return [
            edge.caller
            for edge in self.edges
            if edge.callee == callee
        ]

    def clear(self) -> None:
        self.edges.clear()

    def __contains__(self, symbol: str) -> bool:
        return any(
            edge.caller == symbol or edge.callee == symbol
            for edge in self.edges
        )

    def __len__(self) -> int:
        return len(self.edges)
PY

###############################################################################
# graph/__init__.py
###############################################################################

cat > backend/app/repository/graph/__init__.py <<'PY'
from .call_graph import CallEdge, CallGraph
from .import_graph import ImportEdge, ImportGraph

__all__ = [
    "CallEdge",
    "CallGraph",
    "ImportEdge",
    "ImportGraph",
]
PY

echo
echo "=========================================="
echo " Sprint 06.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_06_02_call_extractor.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"