"""Tests for repository memory capture."""

from __future__ import annotations

import pytest
from pathlib import Path

from app.memory.manager import MemoryManager
from app.memory.config import MemorySettings
from app.memory.repository_capture import capture_repository_insights


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    settings = MemorySettings(
        database_path=tmp_path / "repo_capture.db",
        embedding_provider="local-hash",
        embedding_model="odin-hash-v1",
        embedding_dimensions=64,
    )
    return MemoryManager(settings=settings)


class TestRepositoryCapture:
    def test_capture_creates_memories(self, manager: MemoryManager):
        manifest = {
            "files_indexed": 42,
            "total_bytes": 1024000,
            "summary": {
                "project_purpose": "An autonomous engineering platform",
                "languages": ["Python", "TypeScript"],
                "frameworks": ["FastAPI", "Next.js"],
                "architecture": ["layered", "microservices"],
                "major_modules": [{"name": "backend"}, {"name": "frontend"}],
            },
        }
        ids = capture_repository_insights("ws-001", "odin-core", manifest, manager=manager)
        assert len(ids) > 0

    def test_capture_stores_repository_kind(self, manager: MemoryManager):
        manifest = {
            "files_indexed": 10,
            "total_bytes": 5000,
            "summary": {
                "project_purpose": "Test project",
                "languages": ["Go"],
                "frameworks": ["Gin"],
                "architecture": ["REST"],
                "major_modules": [],
            },
        }
        capture_repository_insights("ws-002", "test-repo", manifest, manager=manager)
        memories = manager.list(repository_id="ws-002")
        assert len(memories) >= 1
        kinds = {m.kind for m in memories}
        assert "repository_discovery" in kinds

    def test_capture_architecture_memories(self, manager: MemoryManager):
        manifest = {
            "files_indexed": 5,
            "total_bytes": 2000,
            "summary": {
                "project_purpose": "Arch test",
                "languages": ["Python"],
                "frameworks": ["FastAPI"],
                "architecture": ["event-driven", "CQRS"],
                "major_modules": [],
            },
        }
        capture_repository_insights("ws-003", "arch-repo", manifest, manager=manager)
        memories = manager.list(repository_id="ws-003")
        arch_memories = [m for m in memories if m.kind == "architecture_decision"]
        assert len(arch_memories) >= 1

    def test_capture_empty_manifest_no_crash(self, manager: MemoryManager):
        ids = capture_repository_insights("ws-004", "empty-repo", None, manager=manager)
        assert ids == []

    def test_capture_no_summary_no_crash(self, manager: MemoryManager):
        ids = capture_repository_insights("ws-005", "no-summary-repo", {}, manager=manager)
        assert ids == []

    def test_capture_deduplication(self, manager: MemoryManager):
        manifest = {
            "files_indexed": 10,
            "total_bytes": 1000,
            "summary": {
                "project_purpose": "Dedup test project",
                "languages": ["Python"],
                "frameworks": ["Flask"],
                "architecture": ["MVC"],
                "major_modules": [],
            },
        }
        ids1 = capture_repository_insights("ws-006", "dedup-repo", manifest, manager=manager)
        ids2 = capture_repository_insights("ws-006", "dedup-repo", manifest, manager=manager)
        # Second capture should return same IDs (deduplication)
        assert set(ids1) == set(ids2)
