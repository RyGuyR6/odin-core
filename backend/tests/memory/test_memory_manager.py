"""Tests for the MemoryManager and memory persistence layer."""

from __future__ import annotations

import pytest
from pathlib import Path

from app.memory.manager import MemoryManager
from app.memory.config import MemorySettings
from app.memory.models import (
    MemoryCreate,
    MemorySearchRequest,
    MemoryUpdate,
    KnowledgeEdgeCreate,
    ConversationMemoryRequest,
    IngestTextRequest,
    ImportRequest,
)
from app.memory.exceptions import MemoryNotFoundError


@pytest.fixture
def settings(tmp_path: Path) -> MemorySettings:
    return MemorySettings(
        database_path=tmp_path / "test_memory.db",
        embedding_provider="local-hash",
        embedding_model="odin-hash-v1",
        embedding_dimensions=64,
        chunk_size=500,
        chunk_overlap=50,
    )


@pytest.fixture
def manager(settings: MemorySettings) -> MemoryManager:
    return MemoryManager(settings=settings)


# ── CRUD ─────────────────────────────────────────────────────────────────────

class TestCreate:
    def test_create_basic(self, manager: MemoryManager):
        req = MemoryCreate(content="Odin uses FastAPI for the backend.", title="Backend stack")
        record = manager.create(req)
        assert record.id.startswith("mem_")
        assert record.content == "Odin uses FastAPI for the backend."
        assert record.title == "Backend stack"
        assert record.kind == "note"
        assert record.scope == "global"
        assert record.version == 1
        assert record.chunk_count >= 1

    def test_create_engineering_kinds(self, manager: MemoryManager):
        for kind in ("architecture_decision", "repository_discovery", "bug_investigation", "fix_resolution"):
            rec = manager.create(MemoryCreate(content=f"Memory of kind {kind}", kind=kind))
            assert rec.kind == kind

    def test_create_with_importance(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Critical decision", importance=0.95, confidence=0.8))
        assert rec.importance == pytest.approx(0.95)
        assert rec.confidence == pytest.approx(0.8)

    def test_create_deduplication(self, manager: MemoryManager):
        req = MemoryCreate(content="Unique content for dedup test", deduplicate=True)
        r1 = manager.create(req)
        r2 = manager.create(req)
        assert r1.id == r2.id

    def test_create_no_dedup_different_content(self, manager: MemoryManager):
        r1 = manager.create(MemoryCreate(content="Content A for no-dedup test", deduplicate=False))
        r2 = manager.create(MemoryCreate(content="Content B for no-dedup test", deduplicate=False))
        assert r1.id != r2.id

    def test_create_with_repository_id(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(
            content="Repository insight",
            kind="repository_discovery",
            repository_id="repo-abc123",
            tags=["python", "fastapi"],
        ))
        assert rec.repository_id == "repo-abc123"
        assert "python" in rec.tags


class TestGet:
    def test_get_existing(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Get me"))
        fetched = manager.get(rec.id)
        assert fetched.id == rec.id
        assert fetched.content == rec.content

    def test_get_missing(self, manager: MemoryManager):
        with pytest.raises(MemoryNotFoundError):
            manager.get("mem_nonexistent")


class TestList:
    def test_list_all(self, manager: MemoryManager):
        for i in range(3):
            manager.create(MemoryCreate(content=f"Item {i}"))
        records = manager.list()
        assert len(records) >= 3

    def test_list_by_scope(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Global item", scope="global"))
        manager.create(MemoryCreate(content="Project item", scope="project", project_id="p1"))
        global_items = manager.list(scope="global")
        assert all(r.scope == "global" for r in global_items)

    def test_list_by_repository_id(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Repo A memory", repository_id="repo-a"))
        manager.create(MemoryCreate(content="Repo B memory", repository_id="repo-b"))
        repo_a = manager.list(repository_id="repo-a")
        assert all(r.repository_id == "repo-a" for r in repo_a)
        assert len(repo_a) >= 1

    def test_list_by_kind(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="An arch decision", kind="architecture_decision"))
        manager.create(MemoryCreate(content="A note", kind="note"))
        arch = manager.list(kind="architecture_decision")
        assert all(r.kind == "architecture_decision" for r in arch)

    def test_list_ordered_by_importance(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Low importance", importance=0.1))
        manager.create(MemoryCreate(content="High importance", importance=0.9))
        records = manager.list()
        importances = [r.importance for r in records]
        assert importances == sorted(importances, reverse=True)

    def test_list_pagination(self, manager: MemoryManager):
        for i in range(5):
            manager.create(MemoryCreate(content=f"Paginate {i}", deduplicate=False))
        page1 = manager.list(limit=3, offset=0)
        page2 = manager.list(limit=3, offset=3)
        assert len(page1) == 3
        ids1 = {r.id for r in page1}
        ids2 = {r.id for r in page2}
        assert ids1.isdisjoint(ids2)


class TestUpdate:
    def test_update_content(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Original"))
        updated = manager.update(rec.id, MemoryUpdate(content="Updated"))
        assert updated.content == "Updated"
        assert updated.version == 2

    def test_update_tags(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Tagged memory"))
        updated = manager.update(rec.id, MemoryUpdate(tags=["a", "b"]))
        assert set(updated.tags) == {"a", "b"}

    def test_update_importance(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Importance update"))
        updated = manager.update(rec.id, MemoryUpdate(importance=0.99))
        assert updated.importance == pytest.approx(0.99)

    def test_update_missing(self, manager: MemoryManager):
        with pytest.raises(MemoryNotFoundError):
            manager.update("mem_bad", MemoryUpdate(content="x"))


class TestDelete:
    def test_delete_existing(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Delete me"))
        result = manager.delete(rec.id)
        assert result["deleted"] is True
        with pytest.raises(MemoryNotFoundError):
            manager.get(rec.id)

    def test_delete_missing(self, manager: MemoryManager):
        with pytest.raises(MemoryNotFoundError):
            manager.delete("mem_nonexistent")


# ── Search ────────────────────────────────────────────────────────────────────

class TestSearch:
    def test_keyword_search(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="FastAPI is a Python web framework"))
        manager.create(MemoryCreate(content="React is a JavaScript library"))
        results = manager.search(MemorySearchRequest(query="FastAPI Python", mode="keyword"))
        assert any("FastAPI" in r.content for r in results)

    def test_semantic_search(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="SQLite database file storage"))
        results = manager.search(MemorySearchRequest(query="database storage", mode="semantic"))
        assert isinstance(results, list)

    def test_hybrid_search(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="pytest unit testing framework"))
        results = manager.search(MemorySearchRequest(query="testing", mode="hybrid"))
        assert isinstance(results, list)

    def test_search_filter_by_scope(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Global scope content", scope="global"))
        manager.create(MemoryCreate(content="Project scope content", scope="project", project_id="p1"))
        results = manager.search(MemorySearchRequest(query="content", mode="keyword", scope="global"))
        assert all(r.scope == "global" for r in results)

    def test_search_filter_by_repository_id(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Repository alpha insight", repository_id="alpha"))
        manager.create(MemoryCreate(content="Repository beta insight", repository_id="beta"))
        results = manager.search(MemorySearchRequest(query="insight", mode="keyword", repository_id="alpha"))
        assert all(r.repository_id == "alpha" for r in results)

    def test_search_result_has_importance(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Important memory", importance=0.8))
        results = manager.search(MemorySearchRequest(query="memory", mode="keyword"))
        assert all(hasattr(r, "importance") for r in results)

    def test_search_limit(self, manager: MemoryManager):
        for i in range(10):
            manager.create(MemoryCreate(content=f"Limit test item {i}", deduplicate=False))
        results = manager.search(MemorySearchRequest(query="limit test", limit=3))
        assert len(results) <= 3

    def test_search_min_score(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Completely unrelated xyz123"))
        results = manager.search(MemorySearchRequest(query="fastapi web", min_score=0.5))
        assert all(r.score >= 0.5 for r in results)


# ── Knowledge Graph ───────────────────────────────────────────────────────────

class TestGraph:
    def test_add_edge(self, manager: MemoryManager):
        a = manager.create(MemoryCreate(content="Node A"))
        b = manager.create(MemoryCreate(content="Node B"))
        edge = manager.add_edge(KnowledgeEdgeCreate(
            source_memory_id=a.id,
            target_memory_id=b.id,
            relation="related_to",
        ))
        assert edge.source_memory_id == a.id
        assert edge.target_memory_id == b.id
        assert edge.relation == "related_to"

    def test_graph_for_memory(self, manager: MemoryManager):
        a = manager.create(MemoryCreate(content="Source node"))
        b = manager.create(MemoryCreate(content="Target node"))
        manager.add_edge(KnowledgeEdgeCreate(source_memory_id=a.id, target_memory_id=b.id, relation="depends_on"))
        edges = manager.graph(a.id)
        assert len(edges) == 1
        assert edges[0].relation == "depends_on"

    def test_graph_all(self, manager: MemoryManager):
        a = manager.create(MemoryCreate(content="A node"))
        b = manager.create(MemoryCreate(content="B node"))
        manager.add_edge(KnowledgeEdgeCreate(source_memory_id=a.id, target_memory_id=b.id, relation="links_to"))
        edges = manager.graph()
        assert len(edges) >= 1

    def test_edge_missing_memory(self, manager: MemoryManager):
        a = manager.create(MemoryCreate(content="Real node"))
        with pytest.raises(MemoryNotFoundError):
            manager.add_edge(KnowledgeEdgeCreate(
                source_memory_id=a.id,
                target_memory_id="mem_ghost",
                relation="broken",
            ))


# ── Ingestion ─────────────────────────────────────────────────────────────────

class TestIngestion:
    def test_ingest_text(self, manager: MemoryManager):
        req = IngestTextRequest(
            text="Ingest this document text.",
            title="Ingested doc",
            kind="document",
            importance=0.7,
        )
        rec = manager.ingest_text(req)
        assert rec.content == "Ingest this document text."
        assert rec.importance == pytest.approx(0.7)

    def test_ingest_file(self, manager: MemoryManager, tmp_path: Path):
        f = tmp_path / "sample.py"
        f.write_text("def hello(): return 'world'")
        rec = manager.ingest_file(str(f))
        assert rec.kind == "code"
        assert "hello" in rec.content

    def test_ingest_file_missing(self, manager: MemoryManager):
        from app.memory.exceptions import IngestionError
        with pytest.raises(IngestionError):
            manager.ingest_file("/nonexistent/path.txt")

    def test_index_conversation(self, manager: MemoryManager):
        req = ConversationMemoryRequest(
            conversation_id="conv-001",
            messages=[
                {"role": "user", "content": "How do I add a new endpoint?"},
                {"role": "assistant", "content": "Create a new route in app/api."},
            ],
            title="Adding endpoint",
        )
        rec = manager.index_conversation(req)
        assert rec.kind == "conversation"
        assert "user" in rec.content.lower()


# ── Export / Import ───────────────────────────────────────────────────────────

class TestExportImport:
    def test_export(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Export me"))
        data = manager.export_data()
        assert "memories" in data
        assert "edges" in data
        assert len(data["memories"]) >= 1

    def test_import(self, manager: MemoryManager):
        data = {
            "memories": [
                {
                    "content": "Imported memory",
                    "kind": "note",
                    "scope": "global",
                    "title": "Import test",
                    "importance": 0.6,
                }
            ]
        }
        result = manager.import_data(ImportRequest(memories=data["memories"]))
        assert result["created"] >= 1

    def test_roundtrip(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Round-trip content", title="RT", importance=0.75))
        export = manager.export_data()
        # Import into a fresh manager
        settings2 = MemorySettings(
            database_path=manager.settings.database_path.parent / "rt.db",
            embedding_provider="local-hash",
            embedding_model="odin-hash-v1",
            embedding_dimensions=64,
        )
        manager2 = MemoryManager(settings=settings2)
        result = manager2.import_data(ImportRequest(memories=export["memories"]))
        assert result["created"] >= 1


# ── Telemetry ─────────────────────────────────────────────────────────────────

class TestTelemetry:
    def test_telemetry_counts(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Telemetry item one"))
        manager.create(MemoryCreate(content="Telemetry item two"))
        tel = manager.telemetry()
        assert tel.memories >= 2
        assert tel.chunks >= 2
        assert tel.database_bytes > 0

    def test_telemetry_by_kind(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="An arch decision", kind="architecture_decision"))
        tel = manager.telemetry()
        assert "architecture_decision" in tel.by_kind

    def test_telemetry_by_scope(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Global one", scope="global"))
        tel = manager.telemetry()
        assert "global" in tel.by_scope

    def test_search_metrics_increment(self, manager: MemoryManager):
        manager.create(MemoryCreate(content="Metric test"))
        manager.search(MemorySearchRequest(query="metric", mode="hybrid"))
        tel = manager.telemetry()
        assert tel.searches >= 1
        assert tel.hybrid_searches >= 1


# ── Access Tracking ───────────────────────────────────────────────────────────

class TestAccessTracking:
    def test_record_access(self, manager: MemoryManager):
        rec = manager.create(MemoryCreate(content="Access me"))
        assert rec.access_count == 0
        manager.record_access(rec.id)
        updated = manager.get(rec.id)
        assert updated.access_count == 1
        assert updated.accessed_at is not None
