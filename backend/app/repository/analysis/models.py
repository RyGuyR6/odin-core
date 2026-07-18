from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnalysisIssue:
    """
    A single issue, finding, or observation produced by an analysis pass.
    """

    severity: str
    message: str
    symbol: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisResult:
    """
    Result produced by a single analysis pass.
    """

    name: str
    issues: list[AnalysisIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0


class AnalysisPass(ABC):
    """
    Base class for all repository analysis passes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def run(self, repository: Any) -> AnalysisResult:
        """
        Execute the analysis pass against a repository.
        """
        raise NotImplementedError
