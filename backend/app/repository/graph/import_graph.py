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
