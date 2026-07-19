#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p odin_mcp/models

cat > odin_mcp/models/decision_graph.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DecisionNode:
    id: str
    title: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DecisionEdge:
    source: str
    target: str
    relationship: str


@dataclass(slots=True)
class DecisionGraph:
    nodes: list[DecisionNode] = field(default_factory=list)
    edges: list[DecisionEdge] = field(default_factory=list)

    def add_node(
        self,
        node_id: str,
        title: str,
        kind: str,
        **metadata: Any,
    ) -> None:

        self.nodes.append(
            DecisionNode(
                id=node_id,
                title=title,
                kind=kind,
                metadata=metadata,
            )
        )

    def connect(
        self,
        source: str,
        target: str,
        relationship: str,
    ) -> None:

        self.edges.append(
            DecisionEdge(
                source=source,
                target=target,
                relationship=relationship,
            )
        )
PY

cat > scripts/test_decision_graph.py <<'PY'
from odin_mcp.models.decision_graph import DecisionGraph

graph = DecisionGraph()

graph.add_node(
    "goal",
    "Add JWT Authentication",
    "goal",
)

graph.add_node(
    "analysis",
    "Repository Analysis",
    "analysis",
)

graph.add_node(
    "plan",
    "Engineering Plan",
    "plan",
)

graph.connect(
    "goal",
    "analysis",
    "analyzed_by",
)

graph.connect(
    "analysis",
    "plan",
    "produced",
)

print(graph)
PY

python -m compileall -q \
    odin_mcp/models/decision_graph.py \
    scripts/test_decision_graph.py

echo
echo "====================================="
echo " Decision Graph Installed"
echo "====================================="
echo
echo "Run:"
echo "python scripts/test_decision_graph.py"
echo
