from __future__ import annotations

from .models import (
    AnalysisIssue,
    AnalysisPass,
    AnalysisResult,
)


class RepositoryHealthAnalysis(AnalysisPass):
    """
    Performs basic repository consistency checks.
    """

    @property
    def name(self) -> str:
        return "repository_health"

    def run(self, repository) -> AnalysisResult:
        result = AnalysisResult(name=self.name)

        if repository.file_count == 0:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="Repository contains no loaded files.",
                )
            )

        if repository.parsed_count != repository.file_count:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="Parsed file count does not match loaded file count.",
                )
            )

        if repository.symbol_count == 0:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="No symbols have been indexed.",
                )
            )

        result.metadata.update(
            {
                "files": repository.file_count,
                "parsed": repository.parsed_count,
                "symbols": repository.symbol_count,
                "imports": len(repository.import_graph),
                "calls": len(repository.call_graph),
            }
        )

        return result
