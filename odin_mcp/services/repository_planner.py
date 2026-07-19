from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from odin_mcp.services.repository_search_service import RepositorySearchService


@dataclass(slots=True)
class CandidateFile:
    path: str
    score: float
    reason: str


@dataclass(slots=True)
class RepositoryAnalysis:
    goal: str
    candidates: list[CandidateFile] = field(default_factory=list)


class RepositoryPlanner:
    """
    Finds the repository locations most relevant to an engineering goal.

    Future versions will combine repository intelligence,
    cross references, embeddings, and LLM reasoning.
    """

    def __init__(
        self,
        repository: RepositorySearchService,
    ) -> None:
        self.repository = repository

    def analyze(
        self,
        goal: str,
    ) -> RepositoryAnalysis:

        analysis = RepositoryAnalysis(goal=goal)

        try:
            matches = self.repository.search_text(goal)

            for match in matches[:20]:
                analysis.candidates.append(
                    CandidateFile(
                        path=match["path"],
                        score=1.0,
                        reason="Text match",
                    )
                )

        except Exception:
            pass

        return analysis
