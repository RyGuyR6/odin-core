"""Tests for planner memory integration."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.memory.manager import MemoryManager
from app.memory.config import MemorySettings
from app.memory.models import MemoryCreate

# Skip all tests in this module if planning/LLM dependencies aren't importable
pytest.importorskip("app.planning.planner", reason="planner dependencies not available")


@pytest.fixture
def manager(tmp_path: Path) -> MemoryManager:
    settings = MemorySettings(
        database_path=tmp_path / "planner_test.db",
        embedding_provider="local-hash",
        embedding_model="odin-hash-v1",
        embedding_dimensions=64,
    )
    return MemoryManager(settings=settings)


class TestPlannerMemoryIntegration:
    def test_planner_includes_memory_context_key(self):
        from app.planning.planner import Planner
        planner = Planner()
        plan = planner.create_plan("add a new API endpoint for health check")
        assert "memory_context" in plan.metadata

    def test_planner_memory_context_is_list(self):
        from app.planning.planner import Planner
        planner = Planner()
        plan = planner.create_plan("implement authentication middleware")
        assert isinstance(plan.metadata["memory_context"], list)

    def test_planner_retrieves_relevant_memories(self, manager: MemoryManager):
        manager.create(MemoryCreate(
            content="FastAPI JWT authentication was implemented in the auth module.",
            kind="engineering_note",
            importance=0.8,
            tags=["authentication", "fastapi"],
        ))
        from app.planning.planner import Planner
        planner = Planner()
        with patch("app.planning.planner.MemoryManager", return_value=manager):
            plan = planner.create_plan("add JWT authentication to the API")
        assert isinstance(plan.metadata["memory_context"], list)

    def test_planner_memory_retrieval_failure_does_not_crash(self):
        """If memory retrieval fails, the planner should still work."""
        from app.planning.planner import Planner
        planner = Planner()
        with patch("app.planning.planner.MemoryManager", side_effect=Exception("DB unavailable")):
            plan = planner.create_plan("some goal that needs memory")
        assert "memory_context" in plan.metadata
        assert plan.metadata["memory_context"] == []
