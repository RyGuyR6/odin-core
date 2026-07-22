from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

MemoryScope = Literal["conversation", "project", "global"]
MemoryKind = Literal[
    "note", "document", "code", "conversation", "decision", "fact", "summary",
    # Engineering-specific kinds added by OIC-011
    "architecture_decision", "repository_discovery", "milestone_history",
    "bug_investigation", "fix_resolution", "user_preference", "engineering_note",
    "coding_pattern", "documentation_insight", "test_strategy", "project_history",
    "ai_reasoning",
]
SearchMode = Literal["semantic", "keyword", "hybrid"]

class MemoryCreate(BaseModel):
    content: str = Field(min_length=1)
    title: str | None = None
    kind: MemoryKind = "note"
    scope: MemoryScope = "global"
    project_id: str | None = None
    repository_id: str | None = None
    conversation_id: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    deduplicate: bool = True

class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    title: str | None = None
    scope: MemoryScope | None = None
    project_id: str | None = None
    repository_id: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

class MemoryRecord(BaseModel):
    id: str
    title: str | None
    content: str
    kind: MemoryKind
    scope: MemoryScope
    project_id: str | None
    repository_id: str | None = None
    conversation_id: str | None
    source: str | None
    tags: list[str]
    metadata: dict[str, Any]
    content_hash: str
    version: int
    importance: float = 0.5
    confidence: float = 1.0
    access_count: int = 0
    accessed_at: datetime | None = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime

class MemoryChunk(BaseModel):
    id: str
    memory_id: str
    ordinal: int
    content: str
    token_count: int
    embedding_model: str
    created_at: datetime

class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: SearchMode = "hybrid"
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    scope: MemoryScope | None = None
    project_id: str | None = None
    repository_id: str | None = None
    conversation_id: str | None = None
    kinds: list[MemoryKind] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

class SearchResult(BaseModel):
    memory_id: str
    chunk_id: str
    title: str | None
    content: str
    kind: MemoryKind
    scope: MemoryScope
    project_id: str | None
    repository_id: str | None = None
    source: str | None
    tags: list[str]
    score: float
    semantic_score: float
    keyword_score: float
    importance: float
    metadata: dict[str, Any]

class IngestTextRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    kind: MemoryKind = "document"
    scope: MemoryScope = "global"
    project_id: str | None = None
    repository_id: str | None = None
    conversation_id: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)

class ReindexRequest(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)

class ImportRequest(BaseModel):
    memories: list[dict[str, Any]]
    replace_existing: bool = False

class KnowledgeEdgeCreate(BaseModel):
    source_memory_id: str
    target_memory_id: str
    relation: str = Field(min_length=1, max_length=100)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

class KnowledgeEdge(BaseModel):
    id: str
    source_memory_id: str
    target_memory_id: str
    relation: str
    weight: float
    metadata: dict[str, Any]
    created_at: datetime

class MemoryTelemetry(BaseModel):
    memories: int
    chunks: int
    edges: int
    embedding_cache_entries: int
    searches: int
    semantic_searches: int
    keyword_searches: int
    hybrid_searches: int
    cache_hits: int
    cache_misses: int
    average_search_ms: float
    database_bytes: int
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_scope: dict[str, int] = Field(default_factory=dict)

class ConversationMemoryRequest(BaseModel):
    conversation_id: str
    messages: list[dict[str, Any]]
    project_id: str | None = None
    title: str | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_messages(self):
        if not self.messages: raise ValueError("At least one message is required")
        return self
