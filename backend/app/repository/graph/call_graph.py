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
