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
