from __future__ import annotations

from .models import ProjectInventory
from .scanner import RepositoryScanner


class IntelligenceEngine:
    def __init__(self) -> None:
        self._scanner = RepositoryScanner()

    def build(self, repository: object) -> ProjectInventory:
        return self._scanner.scan(repository)
