from __future__ import annotations

from collections import defaultdict
import logging
import re
from typing import Any

from app.planning.models import ExecutionPlan, PlanStep
from app.services.repository_context import repository_context_service
from app.services.repository_intelligence import RepositoryScanRecord, repository_intelligence_service

log = logging.getLogger(__name__)

# Phase name constant — used in plan metadata to signal memory retrieval occurred
PHASE_RETRIEVE_MEMORY_CONTEXT = "retrieve_memory_context"
# Maximum content length (chars) included per memory entry in plan metadata
_MEMORY_PLAN_CONTENT_MAX = 500

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

    def _retrieve_memory_context(self, goal: str, repository: str | None) -> list[dict[str, Any]]:
        """Retrieve relevant memories to enrich the plan."""
        try:
            from app.memory import MemoryManager, MemorySearchRequest
            manager = MemoryManager()
            request = MemorySearchRequest(
                query=goal,
                mode="hybrid",
                limit=8,
                min_score=0.1,
            )
            results = manager.search(request)
            return [
                {
                    "memory_id": r.memory_id,
                    "title": r.title,
                    "content": r.content[:_MEMORY_PLAN_CONTENT_MAX],
                    "kind": r.kind,
                    "score": r.score,
                    "importance": r.importance,
                    "tags": r.tags,
                    "source": r.source,
                }
                for r in results
            ]
        except Exception:
            log.debug("Memory retrieval skipped during planning", exc_info=True)
            return []

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
            "memory_context": [],
        }

        # Retrieve relevant memories for this goal (best-effort)
        metadata["memory_context"] = self._retrieve_memory_context(goal, repository)

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
        if metadata["memory_context"]:
            metadata["phases"] = [PHASE_RETRIEVE_MEMORY_CONTEXT] + metadata["phases"]
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

    async def create_ai_plan(
        self,
        goal: str,
        repository: str | None = None,
        profile: str | None = None,
    ) -> ExecutionPlan:
        """Generate an AI-powered execution plan using the LLM platform.

        Builds the same static metadata as create_plan() for context, then
        calls the LLM with structured output enabled to produce a machine-
        readable plan.  The planner never calls OpenAI directly — all
        requests go through LLMService.
        """
        from app.llm.service import get_llm_service  # noqa: PLC0415
        from app.llm.models import ChatMessage, ChatRequest  # noqa: PLC0415

        plan = ExecutionPlan(goal=goal.strip())
        plan.metadata = self._build_metadata(plan.goal, repository)

        service = get_llm_service()
        repo_context = plan.metadata.get("repository_context") or ""
        memory_context = plan.metadata.get("memory_context") or []
        memory_block = ""
        if memory_context:
            memory_block = "\n\nRelevant memories:\n" + "\n".join(
                f"- [{m.get('kind', '?')}] {m.get('title', '')}: {m.get('content', '')[:300]}"
                for m in memory_context[:5]
            )

        system_prompt = (
            "You are Odin, an AI software engineering assistant. "
            "Generate a structured execution plan as a JSON object with the following schema:\n"
            '{"phases": ["string"], "steps": [{"tool": "string", "description": "string", '
            '"parameters": {}}], "notes": ["string"], "candidate_files": ["string"]}\n'
            "Be concise. Focus on actionable steps."
        )
        user_message = f"Goal: {goal}"
        if repo_context:
            user_message += f"\n\nRepository context:\n{repo_context[:4000]}"
        if memory_block:
            user_message += memory_block

        try:
            response = await service.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role="system", content=system_prompt),
                        ChatMessage(role="user", content=user_message),
                    ],
                    integration_point="planner",
                    task_type="planning",
                    execution_profile=(
                        profile if profile in ("economy", "balanced", "maximum")
                        else None
                    ),
                    response_format={"type": "json_object"},
                )
            )
            import json as _json  # noqa: PLC0415
            ai_output = _json.loads(response.content)
            # Merge AI output into plan metadata
            for key in ("phases", "notes", "candidate_files"):
                if key in ai_output and isinstance(ai_output[key], list):
                    plan.metadata[key] = ai_output[key]
            if "steps" in ai_output and isinstance(ai_output["steps"], list):
                for step_data in ai_output["steps"]:
                    if isinstance(step_data, dict):
                        plan.steps.append(
                            PlanStep(
                                tool=step_data.get("tool", "unknown"),
                                parameters=step_data.get("parameters", {}),
                            )
                        )
            plan.metadata["ai_generated"] = True
            plan.metadata["ai_model"] = response.model
        except Exception:
            log.debug("AI plan generation failed; returning static plan", exc_info=True)
            plan.metadata["ai_generated"] = False

        return plan


planner = Planner()
