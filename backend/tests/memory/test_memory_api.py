"""Integration tests for the memory REST API."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

# Skip API tests when full app dependencies (pydantic_settings, openai, etc.) aren't available
pytest.importorskip("pydantic_settings", reason="full app stack not available")

from app.memory.manager import MemoryManager
from app.memory.config import MemorySettings
from fastapi.testclient import TestClient


@pytest.fixture
def memory_manager(tmp_path: Path) -> MemoryManager:
    settings = MemorySettings(
        database_path=tmp_path / "api_test_memory.db",
        embedding_provider="local-hash",
        embedding_model="odin-hash-v1",
        embedding_dimensions=64,
    )
    return MemoryManager(settings=settings)


@pytest.fixture
def client(memory_manager: MemoryManager):
    from app.main import app
    with patch("app.api.memory.get_memory_manager", return_value=memory_manager):
        with TestClient(app) as c:
            yield c


class TestMemoryAPI:
    def test_create_and_get(self, client: TestClient):
        resp = client.post("/memory", json={
            "content": "API test memory",
            "title": "API Test",
            "kind": "note",
            "importance": 0.6,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "API test memory"
        assert data["importance"] == pytest.approx(0.6)
        memory_id = data["id"]

        get_resp = client.get(f"/memory/{memory_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == memory_id

    def test_list(self, client: TestClient):
        client.post("/memory", json={"content": "List item 1"})
        client.post("/memory", json={"content": "List item 2"})
        resp = client.get("/memory")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_list_filter_by_repository_id(self, client: TestClient):
        client.post("/memory", json={"content": "Repo memory", "repository_id": "test-repo"})
        resp = client.get("/memory?repository_id=test-repo")
        assert resp.status_code == 200
        data = resp.json()
        assert all(m["repository_id"] == "test-repo" for m in data)

    def test_search(self, client: TestClient):
        client.post("/memory", json={"content": "SQLAlchemy ORM database access"})
        resp = client.post("/memory/search", json={"query": "database", "mode": "keyword"})
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)

    def test_search_with_kind_filter(self, client: TestClient):
        client.post("/memory", json={"content": "Architecture decision ADR", "kind": "architecture_decision"})
        resp = client.post("/memory/search", json={"query": "architecture", "kinds": ["architecture_decision"]})
        assert resp.status_code == 200

    def test_update(self, client: TestClient):
        create_resp = client.post("/memory", json={"content": "Before update"})
        memory_id = create_resp.json()["id"]
        patch_resp = client.patch(f"/memory/{memory_id}", json={"content": "After update", "importance": 0.9})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["content"] == "After update"
        assert patch_resp.json()["importance"] == pytest.approx(0.9)

    def test_delete(self, client: TestClient):
        create_resp = client.post("/memory", json={"content": "Delete me via API"})
        memory_id = create_resp.json()["id"]
        del_resp = client.delete(f"/memory/{memory_id}")
        assert del_resp.status_code == 200
        get_resp = client.get(f"/memory/{memory_id}")
        assert get_resp.status_code == 404

    def test_telemetry(self, client: TestClient):
        client.post("/memory", json={"content": "Telemetry test"})
        resp = client.get("/memory/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert "by_kind" in data
        assert "by_scope" in data

    def test_engineering_kinds_accepted(self, client: TestClient):
        for kind in ["architecture_decision", "repository_discovery", "bug_investigation", "fix_resolution"]:
            resp = client.post("/memory", json={"content": f"Kind={kind}", "kind": kind, "deduplicate": False})
            assert resp.status_code == 200, f"Failed for kind={kind}"
            assert resp.json()["kind"] == kind

    def test_graph_edges(self, client: TestClient):
        a = client.post("/memory", json={"content": "Graph node A"}).json()["id"]
        b = client.post("/memory", json={"content": "Graph node B"}).json()["id"]
        edge_resp = client.post("/memory/graph/edges", json={
            "source_memory_id": a,
            "target_memory_id": b,
            "relation": "implements",
        })
        assert edge_resp.status_code == 200
        graph_resp = client.get(f"/memory/graph?memory_id={a}")
        assert graph_resp.status_code == 200
        edges = graph_resp.json()
        assert any(e["relation"] == "implements" for e in edges)

    def test_get_missing(self, client: TestClient):
        resp = client.get("/memory/mem_doesnotexist")
        assert resp.status_code == 404

    def test_ingest_text(self, client: TestClient):
        resp = client.post("/memory/ingest/text", json={
            "text": "Ingested document text",
            "title": "Test doc",
            "kind": "document",
            "importance": 0.5,
        })
        assert resp.status_code == 200
        assert resp.json()["kind"] == "document"
