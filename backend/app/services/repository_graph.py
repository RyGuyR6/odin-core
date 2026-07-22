from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.repository_intelligence import repository_intelligence_service


class RepositoryGraphService:
    def query_impact(self, repository: str, path: str) -> dict[str, Any]:
        return repository_intelligence_service.dependency_impact(repository, path)

    def related_tests(self, repository: str, path: str) -> list[str]:
        return self.query_impact(repository, path).get("tests", [])

    def symbol_references(
        self, repository: str, symbol: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return repository_intelligence_service.find_symbol_references(
            repository,
            symbol,
            limit=limit,
        )

    def path_exists(self, repository: str, path: str) -> bool:
        record = repository_intelligence_service.get_scan(repository)
        if record is None or record.payload is None:
            return False
        return any(entry.path == path for entry in record.payload.inventory)

    def module_name(self, path: str) -> str:
        return Path(path).stem


repository_graph_service = RepositoryGraphService()
