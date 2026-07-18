from __future__ import annotations

from .models import AnalysisPass, AnalysisResult
from .results import AnalysisResults


class AnalysisPipeline:
    """
    Executes registered analysis passes against a repository.
    """

    def __init__(self) -> None:
        self._passes: list[AnalysisPass] = []

    def register(self, analysis_pass: AnalysisPass) -> None:
        """
        Register an analysis pass.
        """
        self._passes.append(analysis_pass)

    def unregister(self, name: str) -> bool:
        """
        Remove a registered analysis pass by name.
        """
        before = len(self._passes)
        self._passes = [
            p for p in self._passes
            if p.name != name
        ]
        return len(self._passes) != before

    def clear(self) -> None:
        """
        Remove all registered analysis passes.
        """
        self._passes.clear()

    def run(self, repository) -> list[AnalysisResult]:
        """
        Execute all registered analysis passes.
        """
        results: list[AnalysisResult] = []

        for analysis_pass in self._passes:
            results.append(
                analysis_pass.run(repository)
            )

        return AnalysisResults(results)

    @property
    def passes(self) -> tuple[AnalysisPass, ...]:
        """
        Read-only view of registered passes.
        """
        return tuple(self._passes)

    def __len__(self) -> int:
        return len(self._passes)
