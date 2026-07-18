from __future__ import annotations

from collections import Counter

from .models import AnalysisResult


class AnalysisResults:
    """
    Query API over a collection of AnalysisResult objects.
    """

    def __init__(self, results: list[AnalysisResult]):
        self._results = list(results)

    def all(self) -> list[AnalysisResult]:
        return list(self._results)

    def by_name(self, name: str) -> AnalysisResult | None:
        for result in self._results:
            if result.name == name:
                return result
        return None

    def passed(self) -> list[AnalysisResult]:
        return [r for r in self._results if r.passed]

    def failed(self) -> list[AnalysisResult]:
        return [r for r in self._results if not r.passed]

    def warnings(self):
        warnings = []

        for result in self._results:
            warnings.extend(
                issue
                for issue in result.issues
                if issue.severity.lower() == "warning"
            )

        return warnings

    def errors(self):
        errors = []

        for result in self._results:
            errors.extend(
                issue
                for issue in result.issues
                if issue.severity.lower() == "error"
            )

        return errors

    def summary(self) -> dict[str, int]:
        counter = Counter()

        counter["passes"] = len(self._results)
        counter["passed"] = len(self.passed())
        counter["failed"] = len(self.failed())
        counter["warnings"] = len(self.warnings())
        counter["errors"] = len(self.errors())

        return dict(counter)

    def __iter__(self):
        return iter(self._results)

    def __len__(self):
        return len(self._results)
