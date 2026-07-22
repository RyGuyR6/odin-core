from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from app.planning.models import ExecutionPlan
from app.services.repository_context import repository_context_service
from app.services.repository_intelligence import RepositoryScanRecord, repository_intelligence_service

STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
FRONTEND_TERMS = {"component", "frontend", "page", "route", "ui"}
BACKEND_TERMS = {"api", "backend", "endpoint", "service", "worker"}


class Planner:
    def create_plan(
        self,
        goal: str,
        repository: str | None = None,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(goal=goal.strip())
        plan.metadata = self._build_metadata(plan.goal, repository)
        return plan

    def _build_metadata(
        self,
        goal: str,
        repository: str | None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "phases": [
                "analyze_goal",
                "generate_plan",
                "validate_existing_behavior",
            ],
            "candidate_files": [],
            "notes": [],
            "repository": None,
            "repository_context": None,
            "repository_summary": None,
        }
        if not repository:
            return metadata

        metadata["repository"] = {"full_name": repository}
        scan = repository_intelligence_service.get_scan(repository)
        if scan is None or scan.status != "ready" or scan.payload is None:
            metadata["repository"]["status"] = scan.status if scan else "unavailable"
            metadata["notes"] = [f"Repository intelligence is not ready for {repository}."]
            return metadata

        terms = self._goal_terms(goal)
        candidates = self._candidate_files(scan, terms)
        context_package = repository_context_service.get_context(repository, goal)
        metadata["phases"] = self._phase_sequence(terms, scan, candidates)
        metadata["candidate_files"] = (
            [
                {
                    "path": item.path,
                    "score": item.score,
                    "reasons": [item.match_type, *(["symbol"] if item.symbol else [])],
                }
                for item in context_package.relevant_files
            ]
            or candidates
        )
        metadata["repository"] = {
            "full_name": repository,
            "status": scan.status,
            "local_path": scan.local_path,
        }
        metadata["repository_context"] = repository_context_service.render(context_package)
        metadata["repository_summary"] = context_package.repository_summary
        metadata["repository_package"] = context_package.model_dump(mode="json")
        metadata["affected_symbols"] = context_package.relevant_symbols
        metadata["dependencies"] = context_package.dependency_relationships
        metadata["likely_tests"] = context_package.tests
        metadata["notes"] = context_package.notes or metadata["notes"]
        if not metadata["candidate_files"]:
            metadata["notes"] = [
                "Repository intelligence is available, but no candidate files matched the goal terms.",
            ]
        return metadata

    @staticmethod
    def _goal_terms(goal: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9_]+", goal.lower())
            if len(token) >= 3 and token not in STOPWORDS
        }

    def _phase_sequence(
        self,
        terms: set[str],
        scan: RepositoryScanRecord,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        phases = [
            "analyze_goal",
            "review_repository_intelligence",
            "identify_candidate_files",
        ]
        frameworks = {framework.lower() for framework in scan.payload.summary.frameworks}
        if terms & FRONTEND_TERMS and {"next.js", "react"} & frameworks:
            phases.append("review_frontend_surface")
        if terms & BACKEND_TERMS and "fastapi" in frameworks:
            phases.append("review_backend_surface")
        if candidates:
            phases.append("prioritize_candidate_files")
        phases.extend(["generate_plan", "validate_existing_behavior"])
        return list(dict.fromkeys(phases))

    def _candidate_files(
        self,
        scan: RepositoryScanRecord,
        terms: set[str],
    ) -> list[dict[str, Any]]:
        scores: dict[str, float] = defaultdict(float)
        reasons: dict[str, list[str]] = defaultdict(list)
        payload = scan.payload
        assert payload is not None

        def add(path: str, score: float, reason: str) -> None:
            if not path:
                return
            scores[path] += score
            if reason not in reasons[path]:
                reasons[path].append(reason)

        for symbol in payload.symbols:
            haystack = " ".join(
                value
                for value in (
                    symbol.name,
                    symbol.qualified_name,
                    symbol.module,
                    symbol.container,
                    symbol.file_path,
                )
                if value
            ).lower()
            matched = sorted(term for term in terms if term in haystack)
            if matched:
                add(
                    symbol.file_path,
                    4.0 + len(matched),
                    f"symbol:{', '.join(matched[:3])}",
                )

        for category in payload.architecture:
            category_terms = self._goal_terms(category.category.replace("_", " "))
            if not terms & category_terms:
                continue
            for path in category.files[:12]:
                add(path, 3.0, f"architecture:{category.category}")

        for path in payload.dependency_graph.entry_points:
            matched = sorted(term for term in terms if term in path.lower())
            if matched:
                add(path, 2.0, f"entry_point:{', '.join(matched[:2])}")

        for module in payload.summary.major_modules:
            matched = sorted(term for term in terms if term in module.name.lower())
            if not matched:
                continue
            prefix = module.name.rstrip("/") + "/"
            for entry in payload.inventory:
                if entry.path.startswith(prefix):
                    add(entry.path, 1.5, f"module:{module.name}")

        ranked = sorted(
            (
                {
                    "path": path,
                    "score": round(score, 2),
                    "reasons": reasons[path],
                }
                for path, score in scores.items()
            ),
            key=lambda item: (-item["score"], item["path"]),
        )
        return ranked[:5]


planner = Planner()
