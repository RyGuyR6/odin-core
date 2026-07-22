from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any

from pydantic import BaseModel, Field

from app.services.repository_graph import repository_graph_service
from app.services.repository_intelligence import repository_intelligence_service


class RepositoryContextFile(BaseModel):
    path: str
    score: float
    match_type: str
    symbol: str | None = None
    line: int | None = None


class RepositoryContextPackage(BaseModel):
    repository: str
    indexed_revision: str | None = None
    stale: bool = False
    repository_summary: dict[str, Any] | None = None
    relevant_files: list[RepositoryContextFile] = Field(default_factory=list)
    relevant_symbols: list[dict[str, Any]] = Field(default_factory=list)
    dependency_relationships: list[dict[str, Any]] = Field(default_factory=list)
    documentation: list[dict[str, Any]] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    token_estimate: int = 0


class RepositoryContextService:
    async def aget_context(
        self,
        repository: str,
        objective: str,
        *,
        file_limit: int = 6,
        symbol_limit: int = 8,
        documentation_limit: int = 4,
    ) -> RepositoryContextPackage:
        record = repository_intelligence_service.get_scan(repository)
        if record is None or record.payload is None or record.status != "ready":
            return RepositoryContextPackage(
                repository=repository,
                stale=True,
                notes=[f"Repository intelligence is not ready for {repository}."],
            )

        search = await repository_intelligence_service.search_repository(
            repository,
            objective,
            limit=max(file_limit * 3, 12),
        )
        payload = record.payload
        files: list[RepositoryContextFile] = []
        seen_paths: set[str] = set()
        for item in search["results"]:
            path = str(item["file_path"])
            if path in seen_paths:
                continue
            seen_paths.add(path)
            location = item.get("source_location") or {}
            files.append(
                RepositoryContextFile(
                    path=path,
                    score=float(item["relevance_score"]),
                    match_type=str(item["match_type"]),
                    symbol=item.get("symbol"),
                    line=location.get("line"),
                )
            )
            if len(files) >= file_limit:
                break

        if not files:
            terms = [
                token
                for token in re.findall(r"[a-z0-9_]+", objective.lower())
                if len(token) >= 3
            ]
            for entry in payload.inventory:
                haystack = entry.path.lower()
                if not any(term in haystack for term in terms):
                    continue
                files.append(
                    RepositoryContextFile(
                        path=entry.path,
                        score=24.0,
                        match_type="fallback_path",
                    )
                )
                if len(files) >= file_limit:
                    break

        related_symbols = [
            symbol.model_dump(mode="json")
            for symbol in payload.symbols
            if symbol.file_path in seen_paths
            or objective.lower() in symbol.qualified_name.lower()
        ][:symbol_limit]
        documentation = [
            item
            for item in repository_intelligence_service.list_documentation(
                repository,
                query=objective,
                limit=documentation_limit,
            )
        ]
        relationships = [
            repository_graph_service.query_impact(repository, file.path)
            for file in files[: min(3, len(files))]
        ]
        tests = sorted(
            {test for relation in relationships for test in relation.get("tests", [])}
        )[:8]
        notes: list[str] = []
        stale = bool(search.get("stale")) or repository_intelligence_service.is_stale(
            repository
        )
        if stale:
            notes.append(
                "Repository index may be stale relative to the current workspace revision."
            )
        if not files:
            notes.append("No strongly relevant indexed files matched the objective.")

        summary = payload.summary.model_dump(mode="json")
        rendered_sections = [
            summary.get("project_purpose", ""),
            *[item.path for item in files],
            *[item["excerpt"] for item in documentation],
        ]
        # Use a lightweight chars-to-tokens heuristic so planner/chat callers can
        # bound repository context without making an extra model call.
        token_estimate = sum(
            max(1, len(section) // 4) for section in rendered_sections if section
        )
        return RepositoryContextPackage(
            repository=repository,
            indexed_revision=payload.indexed_revision,
            stale=stale,
            repository_summary=summary,
            relevant_files=files,
            relevant_symbols=related_symbols,
            dependency_relationships=relationships,
            documentation=documentation,
            tests=tests,
            notes=notes,
            token_estimate=token_estimate,
        )

    def get_context(
        self, repository: str, objective: str, **kwargs: Any
    ) -> RepositoryContextPackage:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aget_context(repository, objective, **kwargs))
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: asyncio.run(self.aget_context(repository, objective, **kwargs))
            )
            return future.result()

    @staticmethod
    def render(package: RepositoryContextPackage) -> str:
        summary = package.repository_summary or {}
        files = ", ".join(item.path for item in package.relevant_files[:6]) or "none"
        symbols = (
            ", ".join(
                str(item.get("qualified_name") or item.get("name"))
                for item in package.relevant_symbols[:6]
            )
            or "none"
        )
        tests = ", ".join(package.tests[:6]) or "none"
        docs = (
            ", ".join(str(item.get("path")) for item in package.documentation[:4])
            or "none"
        )
        notes = " ".join(package.notes)
        return "\n".join(
            [
                f"Repository: {package.repository}",
                f"Indexed revision: {package.indexed_revision or 'unknown'}",
                f"Purpose: {summary.get('project_purpose', 'unknown')}",
                f"Relevant files: {files}",
                f"Relevant symbols: {symbols}",
                f"Related tests: {tests}",
                f"Documentation: {docs}",
                f"Notes: {notes or 'none'}",
            ]
        )


repository_context_service = RepositoryContextService()
