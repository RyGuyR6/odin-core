from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from app.planning.models import ExecutionPlan
from app.services.repository_intelligence import (
    RepositoryScanRecord,
    repository_intelligence_service,
)

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
FRONTEND_TERMS = {"component", "frontend", "page", "ui"}
BACKEND_TERMS = {"api", "backend", "endpoint", "service", "worker"}
SUPPORTED_FRONTEND_FRAMEWORKS = {"next.js", "react"}
SUPPORTED_BACKEND_FRAMEWORKS = {"django", "express", "fastapi", "flask"}
MAX_ARCHITECTURE_FILES_PER_CATEGORY = 12
MAX_CANDIDATE_FILES = 5


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
        if scan is None:
            metadata["repository"]["status"] = "unavailable"
            metadata["notes"] = [f"Repository intelligence is not ready for {repository}."]
            return metadata
        if scan.status != "ready" or scan.payload is None:
            metadata["repository"]["status"] = scan.status
            metadata["notes"] = [f"Repository intelligence is not ready for {repository}."]
            return metadata

        terms = self._goal_terms(goal)
        frameworks = {
            framework.lower()
            for framework in scan.payload.summary.frameworks
        }
        candidates = self._candidate_files(scan, terms)
        metadata["phases"] = self._phase_sequence(terms, frameworks, candidates)
        metadata["candidate_files"] = candidates
        metadata["repository"] = {
            "full_name": repository,
            "status": scan.status,
            "local_path": scan.local_path,
        }
        metadata["repository_context"] = repository_intelligence_service.render_repository_context(
            repository
        )
        metadata["repository_summary"] = scan.payload.summary.model_dump(mode="json")
        if not candidates:
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
        frameworks: set[str],
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        phases = [
            "analyze_goal",
            "review_repository_intelligence",
            "identify_candidate_files",
        ]
        if terms & FRONTEND_TERMS and SUPPORTED_FRONTEND_FRAMEWORKS & frameworks:
            phases.append("review_frontend_surface")
        if terms & BACKEND_TERMS and SUPPORTED_BACKEND_FRAMEWORKS & frameworks:
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
        inventory_by_module: dict[str, list[str]] = defaultdict(list)
        for entry in payload.inventory:
            top_level = entry.path.split("/", 1)[0]
            inventory_by_module[top_level].append(entry.path)

        def add(path: str, score: float, reason: str) -> None:
            if not path:
                return
            scores[path] += score
            if reason not in reasons[path]:
                reasons[path].append(reason)

        for symbol in payload.symbols:
            haystack = self._symbol_match_text(symbol)
            matched = sorted(term for term in terms if term in haystack)
            if matched:
                add(
                    symbol.file_path,
                    4.0 + len(matched),
                    f"symbol:{', '.join(matched[:3])}",
                )

        for category in payload.architecture:
            if not category.files:
                continue
            category_terms = self._goal_terms(category.category.replace("_", " "))
            if not terms & category_terms:
                continue
            for path in category.files[:MAX_ARCHITECTURE_FILES_PER_CATEGORY]:
                add(path, 3.0, f"architecture:{category.category}")

        for path in payload.dependency_graph.entry_points:
            matched = sorted(term for term in terms if term in path.lower())
            if matched:
                add(path, 2.0, f"entry_point:{', '.join(matched[:2])}")

        for module in payload.summary.major_modules:
            matched = sorted(term for term in terms if term in module.name.lower())
            if not matched:
                continue
            for path in inventory_by_module.get(module.name, []):
                add(path, 1.5, f"module:{module.name}")

        ranked = sorted(
            (
                self._candidate_entry(
                    path=path,
                    score=score,
                    reasons=reasons[path],
                )
                for path, score in scores.items()
            ),
            key=lambda item: (-item["score"], item["path"]),
        )
        return ranked[:MAX_CANDIDATE_FILES]

    @staticmethod
    def _symbol_match_text(symbol: Any) -> str:
        return " ".join(
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

    @staticmethod
    def _candidate_entry(
        *,
        path: str,
        score: float,
        reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "path": path,
            "score": round(score, 2),
            "reasons": reasons,
        }


planner = Planner()
