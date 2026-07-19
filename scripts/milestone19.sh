#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
PASS_COUNT=0
SKIP_COUNT=0
ROLLBACK_DONE=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ PASS_COUNT=$((PASS_COUNT+1)); printf '✅ %s\n' "$1"; }
skip(){ SKIP_COUNT=$((SKIP_COUNT+1)); printf '⏭️  %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="$1"
  trap - ERR
  if [[ "${ROLLBACK_DONE:-0}" == "1" ]]; then exit "$code"; fi
  ROLLBACK_DONE=1
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 19 changes...\n'
    while IFS= read -r -d '' meta; do
      rel="${meta#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$meta" == *.missing ]]; then rm -rf "$target"; else mkdir -p "$(dirname "$target")"; cp -a "$meta" "$target"; fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 19 FAILED\nLine: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for d in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$d" ]] || continue
  if [[ -d "$d/backend/app" ]]; then ROOT="$(cd "$d" && pwd)"; BACKEND="$ROOT/backend"; break; fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core. Run from the repository root or set ODIN_ROOT."
for p in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$p" && -x "$p" ]] && PYTHON_BIN="$p" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 19 — LONG-TERM MEMORY & KNOWLEDGE STORE\n'
printf '============================================================\n\n'
printf 'Repository: %s\nBackend:    %s\nBranch:     %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$(git -C "$ROOT" branch --show-current 2>/dev/null || echo unknown)" "$PYTHON_BIN"

step "Checking Milestones 15–18"
[[ -f "$BACKEND/app/main.py" ]] || die "backend/app/main.py is missing"
[[ -d "$BACKEND/app/llm" ]] || die "Milestone 15 LLM subsystem is missing"
[[ -d "$BACKEND/app/prompts" ]] || die "Milestone 16 prompt subsystem is missing"
[[ -d "$BACKEND/app/conversations" ]] || die "Milestone 17 conversation subsystem is missing"
[[ -d "$BACKEND/app/agents" ]] || die "Milestone 18 agent runtime is missing"
ok "Required foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone19/$STAMP"
mkdir -p "$BACKUP_DIR/files"
backup_path(){
  local target="$1"
  local dest="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$target" ]]; then cp -a "$target" "$dest"; else : > "${dest}.missing"; fi
}
for path in "$BACKEND/app/memory" "$BACKEND/app/api/memory.py" "$BACKEND/app/main.py" "$ROOT/.env.example"; do backup_path "$path"; done
ok "Backup created at $BACKUP_DIR"

step "Creating Long-Term Memory subsystem"
mkdir -p "$BACKEND/app/memory" "$BACKEND/app/api"
cat > "$BACKEND/app/memory/__init__.py" <<'PY'
"""Persistent long-term memory and knowledge retrieval for Odin."""
from .manager import MemoryManager, get_memory_manager
from .models import MemoryCreate, MemoryRecord, MemorySearchRequest, SearchResult

__all__ = ["MemoryManager", "get_memory_manager", "MemoryCreate", "MemoryRecord", "MemorySearchRequest", "SearchResult"]
PY
cat > "$BACKEND/app/memory/exceptions.py" <<'PY'
class MemoryError(Exception):
    """Base exception for the memory subsystem."""

class MemoryNotFoundError(MemoryError):
    pass

class MemoryValidationError(MemoryError):
    pass

class IngestionError(MemoryError):
    pass

class EmbeddingError(MemoryError):
    pass
PY
cat > "$BACKEND/app/memory/config.py" <<'PY'
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(slots=True)
class MemorySettings:
    database_path: Path = field(default_factory=lambda: Path(os.getenv("ODIN_MEMORY_DB", Path(__file__).resolve().parents[2] / "data" / "memory.db")))
    embedding_provider: str = field(default_factory=lambda: os.getenv("ODIN_MEMORY_EMBEDDING_PROVIDER", "local-hash"))
    embedding_model: str = field(default_factory=lambda: os.getenv("ODIN_MEMORY_EMBEDDING_MODEL", "odin-hash-v1"))
    embedding_dimensions: int = field(default_factory=lambda: int(os.getenv("ODIN_MEMORY_EMBEDDING_DIMENSIONS", "256")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("ODIN_MEMORY_CHUNK_SIZE", "1200")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("ODIN_MEMORY_CHUNK_OVERLAP", "180")))
    default_limit: int = field(default_factory=lambda: int(os.getenv("ODIN_MEMORY_SEARCH_LIMIT", "10")))
    max_limit: int = field(default_factory=lambda: int(os.getenv("ODIN_MEMORY_SEARCH_MAX_LIMIT", "100")))
    auto_index_conversations: bool = field(default_factory=lambda: os.getenv("ODIN_MEMORY_AUTO_INDEX_CONVERSATIONS", "false").lower() in {"1","true","yes"})

def get_memory_settings() -> MemorySettings:
    settings = MemorySettings()
    if settings.embedding_dimensions < 32: raise ValueError("ODIN_MEMORY_EMBEDDING_DIMENSIONS must be at least 32")
    if settings.chunk_overlap >= settings.chunk_size: raise ValueError("Chunk overlap must be smaller than chunk size")
    return settings
PY
cat > "$BACKEND/app/memory/models.py" <<'PY'
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

MemoryScope = Literal["conversation", "project", "global"]
MemoryKind = Literal["note", "document", "code", "conversation", "decision", "fact", "summary"]
SearchMode = Literal["semantic", "keyword", "hybrid"]

class MemoryCreate(BaseModel):
    content: str = Field(min_length=1)
    title: str | None = None
    kind: MemoryKind = "note"
    scope: MemoryScope = "global"
    project_id: str | None = None
    conversation_id: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    deduplicate: bool = True

class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1)
    title: str | None = None
    scope: MemoryScope | None = None
    project_id: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

class MemoryRecord(BaseModel):
    id: str
    title: str | None
    content: str
    kind: MemoryKind
    scope: MemoryScope
    project_id: str | None
    conversation_id: str | None
    source: str | None
    tags: list[str]
    metadata: dict[str, Any]
    content_hash: str
    version: int
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
    source: str | None
    tags: list[str]
    score: float
    semantic_score: float
    keyword_score: float
    metadata: dict[str, Any]

class IngestTextRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str | None = None
    kind: MemoryKind = "document"
    scope: MemoryScope = "global"
    project_id: str | None = None
    conversation_id: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

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
PY
cat > "$BACKEND/app/memory/chunking.py" <<'PY'
from __future__ import annotations
import re
from dataclasses import dataclass

@dataclass(slots=True)
class TextChunk:
    ordinal: int
    content: str
    token_count: int

def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 180) -> list[TextChunk]:
    text = text.strip()
    if not text: return []
    if overlap < 0 or overlap >= chunk_size: raise ValueError("overlap must be >= 0 and smaller than chunk_size")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            pieces.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + chunk_size)
            if end < len(paragraph):
                boundary = max(paragraph.rfind(". ", start, end), paragraph.rfind("\n", start, end), paragraph.rfind(" ", start, end))
                if boundary > start + chunk_size // 2: end = boundary + 1
            pieces.append(paragraph[start:end].strip())
            if end >= len(paragraph): break
            start = max(start + 1, end - overlap)
    chunks: list[TextChunk] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else current + "\n\n" + piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current: chunks.append(TextChunk(len(chunks), current, estimate_tokens(current)))
            prefix = current[-overlap:] if current and overlap else ""
            current = (prefix + "\n" + piece).strip() if prefix else piece
            while len(current) > chunk_size:
                segment = current[:chunk_size]
                chunks.append(TextChunk(len(chunks), segment, estimate_tokens(segment)))
                current = current[max(1, chunk_size-overlap):]
    if current: chunks.append(TextChunk(len(chunks), current, estimate_tokens(current)))
    return chunks
PY
cat > "$BACKEND/app/memory/embeddings.py" <<'PY'
from __future__ import annotations
import hashlib, math, re
from dataclasses import dataclass

@dataclass(slots=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    dimensions: int

class LocalHashEmbedder:
    """Deterministic, dependency-free semantic-ish embeddings for local operation and tests."""
    def __init__(self, dimensions: int = 256, model: str = "odin-hash-v1"):
        self.dimensions = dimensions; self.model = model
    def embed(self, text: str) -> EmbeddingResult:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        for token in tokens:
            for feature in {token, *[token[i:i+3] for i in range(max(0, len(token)-2))]}:
                digest = hashlib.blake2b(feature.encode(), digest_size=16).digest()
                idx = int.from_bytes(digest[:8], "big") % self.dimensions
                sign = 1.0 if digest[8] & 1 else -1.0
                vector[idx] += sign
        norm = math.sqrt(sum(v*v for v in vector))
        if norm: vector = [v/norm for v in vector]
        return EmbeddingResult(vector, self.model, self.dimensions)

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a: return 0.0
    return max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b))))

def get_embedder(provider: str, model: str, dimensions: int):
    # local-hash is intentionally always available. External provider adapters can
    # be introduced later without changing persistence or retrieval interfaces.
    if provider not in {"local-hash", "hash", "local"}:
        raise ValueError(f"Unsupported memory embedding provider: {provider}")
    return LocalHashEmbedder(dimensions=dimensions, model=model)
PY
cat > "$BACKEND/app/memory/persistence.py" <<'PY'
from __future__ import annotations
import json, sqlite3, threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

def utcnow() -> str: return datetime.now(timezone.utc).isoformat()

class MemoryStore:
    def __init__(self, path: Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._lock = threading.RLock(); self.initialize()
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON"); db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA busy_timeout=30000")
        try: yield db; db.commit()
        except Exception: db.rollback(); raise
        finally: db.close()
    def initialize(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY, title TEXT, content TEXT NOT NULL, kind TEXT NOT NULL, scope TEXT NOT NULL,
              project_id TEXT, conversation_id TEXT, source TEXT, tags_json TEXT NOT NULL DEFAULT '[]',
              metadata_json TEXT NOT NULL DEFAULT '{}', content_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_hash_scope_project ON memories(content_hash, scope, COALESCE(project_id,''));
            CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_memories_conversation ON memories(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
            CREATE TABLE IF NOT EXISTS memory_chunks (
              id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
              ordinal INTEGER NOT NULL, content TEXT NOT NULL, token_count INTEGER NOT NULL,
              embedding_json TEXT NOT NULL, embedding_model TEXT NOT NULL, created_at TEXT NOT NULL,
              UNIQUE(memory_id, ordinal)
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_memory ON memory_chunks(memory_id);
            CREATE TABLE IF NOT EXISTS embedding_cache (
              cache_key TEXT PRIMARY KEY, content_hash TEXT NOT NULL, model TEXT NOT NULL,
              dimensions INTEGER NOT NULL, embedding_json TEXT NOT NULL, hit_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, last_used_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_edges (
              id TEXT PRIMARY KEY, source_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
              target_memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
              relation TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
              UNIQUE(source_memory_id, target_memory_id, relation)
            );
            CREATE TABLE IF NOT EXISTS memory_metrics (
              key TEXT PRIMARY KEY, value REAL NOT NULL DEFAULT 0
            );
            ''')
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(chunk_id UNINDEXED, memory_id UNINDEXED, title, content, tags)")
            except sqlite3.OperationalError:
                pass
    def metric_inc(self, key: str, value: float = 1.0):
        with self.connect() as db:
            db.execute("INSERT INTO memory_metrics(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+excluded.value", (key,value))
    def metric_get(self, key: str) -> float:
        with self.connect() as db:
            row=db.execute("SELECT value FROM memory_metrics WHERE key=?",(key,)).fetchone(); return float(row["value"]) if row else 0.0
    def sync_fts_for_memory(self, memory_id: str):
        with self.connect() as db:
            try:
                db.execute("DELETE FROM memory_fts WHERE memory_id=?",(memory_id,))
                rows=db.execute("SELECT c.id chunk_id,c.memory_id,m.title,c.content,m.tags_json FROM memory_chunks c JOIN memories m ON m.id=c.memory_id WHERE c.memory_id=?",(memory_id,)).fetchall()
                for r in rows:
                    tags=" ".join(json.loads(r["tags_json"])); db.execute("INSERT INTO memory_fts(chunk_id,memory_id,title,content,tags) VALUES(?,?,?,?,?)",(r["chunk_id"],r["memory_id"],r["title"] or "",r["content"],tags))
            except sqlite3.OperationalError: pass
PY
cat > "$BACKEND/app/memory/retrieval.py" <<'PY'
from __future__ import annotations
import json, math, re
from .embeddings import cosine_similarity

def keyword_similarity(query: str, text: str) -> float:
    q=set(re.findall(r"[a-z0-9_]+",query.lower())); t=set(re.findall(r"[a-z0-9_]+",text.lower()))
    if not q: return 0.0
    return len(q & t) / len(q)

def combine_scores(semantic: float, keyword: float, mode: str) -> float:
    semantic=max(0.0,(semantic+1.0)/2.0)
    if mode == "semantic": return semantic
    if mode == "keyword": return keyword
    return 0.68*semantic + 0.32*keyword

def metadata_matches(row, request) -> bool:
    if request.scope and row["scope"] != request.scope: return False
    if request.project_id and row["project_id"] != request.project_id: return False
    if request.conversation_id and row["conversation_id"] != request.conversation_id: return False
    if request.kinds and row["kind"] not in request.kinds: return False
    tags=json.loads(row["tags_json"])
    if request.tags and not set(request.tags).issubset(set(tags)): return False
    return True
PY
cat > "$BACKEND/app/memory/manager.py" <<'PY'
from __future__ import annotations
import hashlib, json, time, uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from .chunking import chunk_text
from .config import MemorySettings, get_memory_settings
from .embeddings import get_embedder, cosine_similarity
from .exceptions import MemoryNotFoundError, MemoryValidationError, IngestionError
from .models import *
from .persistence import MemoryStore, utcnow
from .retrieval import keyword_similarity, combine_scores, metadata_matches

def _id(prefix: str) -> str: return f"{prefix}_{uuid.uuid4().hex}"
def _hash(text: str) -> str: return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _record(row, chunk_count=0):
    return MemoryRecord(id=row["id"],title=row["title"],content=row["content"],kind=row["kind"],scope=row["scope"],project_id=row["project_id"],conversation_id=row["conversation_id"],source=row["source"],tags=json.loads(row["tags_json"]),metadata=json.loads(row["metadata_json"]),content_hash=row["content_hash"],version=row["version"],chunk_count=chunk_count,created_at=row["created_at"],updated_at=row["updated_at"])

class MemoryManager:
    def __init__(self, settings: MemorySettings | None = None):
        self.settings=settings or get_memory_settings(); self.store=MemoryStore(self.settings.database_path)
        self.embedder=get_embedder(self.settings.embedding_provider,self.settings.embedding_model,self.settings.embedding_dimensions)
    def _embedding(self, text: str) -> list[float]:
        content_hash=_hash(text); cache_key=_hash(f"{self.embedder.model}:{content_hash}")
        cached = None
        with self.store.connect() as db:
            row=db.execute("SELECT embedding_json FROM embedding_cache WHERE cache_key=?",(cache_key,)).fetchone()
            if row:
                db.execute("UPDATE embedding_cache SET hit_count=hit_count+1,last_used_at=? WHERE cache_key=?",(utcnow(),cache_key))
                cached = json.loads(row["embedding_json"])
        if cached is not None:
            self.store.metric_inc("cache_hits")
            return cached
        result=self.embedder.embed(text)
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO embedding_cache(cache_key,content_hash,model,dimensions,embedding_json,hit_count,created_at,last_used_at) VALUES(?,?,?,?,?,0,?,?)",(cache_key,content_hash,result.model,result.dimensions,json.dumps(result.vector),utcnow(),utcnow()))
        self.store.metric_inc("cache_misses"); return result.vector
    def _index(self, memory_id: str, content: str):
        chunks=chunk_text(content,self.settings.chunk_size,self.settings.chunk_overlap)
        indexed=[(ch,self._embedding(ch.content)) for ch in chunks]
        with self.store.connect() as db:
            db.execute("DELETE FROM memory_chunks WHERE memory_id=?",(memory_id,))
            for ch, embedding in indexed:
                db.execute("INSERT INTO memory_chunks(id,memory_id,ordinal,content,token_count,embedding_json,embedding_model,created_at) VALUES(?,?,?,?,?,?,?,?)",(_id("chk"),memory_id,ch.ordinal,ch.content,ch.token_count,json.dumps(embedding),self.embedder.model,utcnow()))
        self.store.sync_fts_for_memory(memory_id)
        return len(chunks)
    def create(self, request: MemoryCreate) -> MemoryRecord:
        content=request.content.strip(); digest=_hash(content)
        if request.deduplicate:
            with self.store.connect() as db:
                row=db.execute("SELECT * FROM memories WHERE content_hash=? AND scope=? AND COALESCE(project_id,'')=COALESCE(?,'')",(digest,request.scope,request.project_id)).fetchone()
                if row: return self.get(row["id"])
        memory_id=_id("mem"); now=utcnow()
        with self.store.connect() as db:
            db.execute("INSERT INTO memories(id,title,content,kind,scope,project_id,conversation_id,source,tags_json,metadata_json,content_hash,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(memory_id,request.title,content,request.kind,request.scope,request.project_id,request.conversation_id,request.source,json.dumps(sorted(set(request.tags))),json.dumps(request.metadata),digest,1,now,now))
        self._index(memory_id,content); return self.get(memory_id)
    def get(self, memory_id: str) -> MemoryRecord:
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM memories WHERE id=?",(memory_id,)).fetchone()
            if not row: raise MemoryNotFoundError(memory_id)
            count=db.execute("SELECT COUNT(*) n FROM memory_chunks WHERE memory_id=?",(memory_id,)).fetchone()["n"]
        return _record(row,count)
    def list(self, *, limit=100, offset=0, scope=None, project_id=None, kind=None):
        clauses=[]; params=[]
        for col,val in (("scope",scope),("project_id",project_id),("kind",kind)):
            if val is not None: clauses.append(f"{col}=?"); params.append(val)
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        with self.store.connect() as db:
            rows=db.execute(f"SELECT m.*, (SELECT COUNT(*) FROM memory_chunks c WHERE c.memory_id=m.id) chunk_count FROM memories m{where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",(*params,min(limit,self.settings.max_limit),offset)).fetchall()
        return [_record(r,r["chunk_count"]) for r in rows]
    def update(self, memory_id: str, request: MemoryUpdate):
        current=self.get(memory_id); data=request.model_dump(exclude_unset=True); content=data.pop("content",None)
        columns=[]; params=[]
        for key,val in data.items():
            column={"tags":"tags_json","metadata":"metadata_json"}.get(key,key)
            if key in {"tags","metadata"}: val=json.dumps(val)
            columns.append(f"{column}=?"); params.append(val)
        if content is not None:
            content=content.strip(); columns += ["content=?","content_hash=?","version=version+1"]; params += [content,_hash(content)]
        columns.append("updated_at=?"); params.append(utcnow()); params.append(memory_id)
        with self.store.connect() as db: db.execute(f"UPDATE memories SET {', '.join(columns)} WHERE id=?",params)
        if content is not None: self._index(memory_id,content)
        elif "tags" in data: self.store.sync_fts_for_memory(memory_id)
        return self.get(memory_id)
    def delete(self, memory_id: str):
        self.get(memory_id)
        with self.store.connect() as db:
            try: db.execute("DELETE FROM memory_fts WHERE memory_id=?",(memory_id,))
            except Exception: pass
            db.execute("DELETE FROM memories WHERE id=?",(memory_id,))
        return {"deleted": True, "id": memory_id}
    def search(self, request: MemorySearchRequest):
        started=time.perf_counter(); query_vector=self._embedding(request.query) if request.mode in {"semantic","hybrid"} else []
        with self.store.connect() as db:
            rows=db.execute("SELECT c.id chunk_id,c.content chunk_content,c.embedding_json,m.* FROM memory_chunks c JOIN memories m ON m.id=c.memory_id").fetchall()
        results=[]
        for row in rows:
            if not metadata_matches(row,request): continue
            sem=cosine_similarity(query_vector,json.loads(row["embedding_json"])) if query_vector else 0.0
            kw=keyword_similarity(request.query," ".join([row["title"] or "",row["chunk_content"]," ".join(json.loads(row["tags_json"]))]))
            score=combine_scores(sem,kw,request.mode)
            if score < request.min_score: continue
            results.append(SearchResult(memory_id=row["id"],chunk_id=row["chunk_id"],title=row["title"],content=row["chunk_content"],kind=row["kind"],scope=row["scope"],project_id=row["project_id"],source=row["source"],tags=json.loads(row["tags_json"]),score=round(score,6),semantic_score=round(max(0,(sem+1)/2),6),keyword_score=round(kw,6),metadata=json.loads(row["metadata_json"])))
        results.sort(key=lambda x:x.score,reverse=True)
        elapsed=(time.perf_counter()-started)*1000; self.store.metric_inc("searches"); self.store.metric_inc(f"{request.mode}_searches"); self.store.metric_inc("search_ms_total",elapsed)
        return results[:min(request.limit,self.settings.max_limit)]
    def reindex(self, memory_ids: list[str] | None=None):
        records=[self.get(mid) for mid in memory_ids] if memory_ids else self.list(limit=self.settings.max_limit)
        count=0
        for rec in records: count += self._index(rec.id,rec.content)
        return {"memories":len(records),"chunks":count}
    def ingest_text(self, request: IngestTextRequest):
        return self.create(MemoryCreate(**request.model_dump()))
    def ingest_file(self, path: str, *, scope="global",project_id=None,tags=None):
        p=Path(path).expanduser().resolve()
        if not p.is_file(): raise IngestionError(f"File not found: {p}")
        if p.stat().st_size > 10*1024*1024: raise IngestionError("File exceeds 10 MiB ingestion limit")
        ext=p.suffix.lower()
        if ext==".pdf":
            try:
                from pypdf import PdfReader
                text="\n\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)
            except ImportError as exc: raise IngestionError("PDF ingestion requires pypdf") from exc
        else: text=p.read_text(encoding="utf-8",errors="replace")
        kind="code" if ext in {".py",".js",".ts",".tsx",".java",".go",".rs",".sh"} else "document"
        return self.create(MemoryCreate(content=text,title=p.name,kind=kind,scope=scope,project_id=project_id,source=str(p),tags=tags or [],metadata={"extension":ext,"size_bytes":p.stat().st_size}))
    def index_conversation(self, request: ConversationMemoryRequest):
        lines=[]
        for msg in request.messages:
            role=str(msg.get("role","unknown")).upper(); content=str(msg.get("content","")).strip()
            if content: lines.append(f"{role}: {content}")
        return self.create(MemoryCreate(content="\n\n".join(lines),title=request.title or f"Conversation {request.conversation_id}",kind="conversation",scope="project" if request.project_id else "conversation",project_id=request.project_id,conversation_id=request.conversation_id,source="conversation",tags=request.tags,metadata={"message_count":len(request.messages)}))
    def add_edge(self, request: KnowledgeEdgeCreate):
        self.get(request.source_memory_id); self.get(request.target_memory_id); edge_id=_id("edge")
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO knowledge_edges(id,source_memory_id,target_memory_id,relation,weight,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",(edge_id,request.source_memory_id,request.target_memory_id,request.relation,request.weight,json.dumps(request.metadata),utcnow()))
        return self.get_edge(edge_id)
    def get_edge(self, edge_id):
        with self.store.connect() as db: row=db.execute("SELECT * FROM knowledge_edges WHERE id=?",(edge_id,)).fetchone()
        if not row: raise MemoryNotFoundError(edge_id)
        return KnowledgeEdge(id=row["id"],source_memory_id=row["source_memory_id"],target_memory_id=row["target_memory_id"],relation=row["relation"],weight=row["weight"],metadata=json.loads(row["metadata_json"]),created_at=row["created_at"])
    def graph(self, memory_id: str|None=None):
        with self.store.connect() as db:
            if memory_id: rows=db.execute("SELECT * FROM knowledge_edges WHERE source_memory_id=? OR target_memory_id=? ORDER BY created_at",(memory_id,memory_id)).fetchall()
            else: rows=db.execute("SELECT * FROM knowledge_edges ORDER BY created_at LIMIT 1000").fetchall()
        return [KnowledgeEdge(id=r["id"],source_memory_id=r["source_memory_id"],target_memory_id=r["target_memory_id"],relation=r["relation"],weight=r["weight"],metadata=json.loads(r["metadata_json"]),created_at=r["created_at"]) for r in rows]
    def export_data(self): return {"version":1,"memories":[r.model_dump(mode="json") for r in self.list(limit=self.settings.max_limit)],"edges":[e.model_dump(mode="json") for e in self.graph()]}
    def import_data(self, request: ImportRequest):
        created=updated=0
        for item in request.memories:
            original_id=item.get("id")
            try:
                existing=self.get(original_id) if original_id else None
            except MemoryNotFoundError: existing=None
            payload=MemoryCreate(content=item["content"],title=item.get("title"),kind=item.get("kind","note"),scope=item.get("scope","global"),project_id=item.get("project_id"),conversation_id=item.get("conversation_id"),source=item.get("source"),tags=item.get("tags",[]),metadata=item.get("metadata",{}),deduplicate=not request.replace_existing)
            if existing and request.replace_existing: self.update(existing.id,MemoryUpdate(content=payload.content,title=payload.title,tags=payload.tags,metadata=payload.metadata)); updated+=1
            else: self.create(payload); created+=1
        return {"created":created,"updated":updated}
    def telemetry(self):
        with self.store.connect() as db:
            counts={name:db.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"] for name,table in (("memories","memories"),("chunks","memory_chunks"),("edges","knowledge_edges"),("embedding_cache_entries","embedding_cache"))}
        searches=int(self.store.metric_get("searches")); avg=self.store.metric_get("search_ms_total")/searches if searches else 0.0
        return MemoryTelemetry(**counts,searches=searches,semantic_searches=int(self.store.metric_get("semantic_searches")),keyword_searches=int(self.store.metric_get("keyword_searches")),hybrid_searches=int(self.store.metric_get("hybrid_searches")),cache_hits=int(self.store.metric_get("cache_hits")),cache_misses=int(self.store.metric_get("cache_misses")),average_search_ms=round(avg,3),database_bytes=self.settings.database_path.stat().st_size if self.settings.database_path.exists() else 0)

@lru_cache(maxsize=1)
def get_memory_manager(): return MemoryManager()
PY
cat > "$BACKEND/app/api/memory.py" <<'PY'
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from app.memory.exceptions import MemoryError, MemoryNotFoundError
from app.memory.manager import MemoryManager, get_memory_manager
from app.memory.models import *

router=APIRouter(prefix="/memory",tags=["memory"])
def manager_dep(): return get_memory_manager()
def guard(call):
    try: return call()
    except MemoryNotFoundError as exc: raise HTTPException(404,str(exc))
    except (MemoryError,ValueError) as exc: raise HTTPException(400,str(exc))

@router.post("",response_model=MemoryRecord)
def create_memory(request:MemoryCreate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.create(request))
@router.get("",response_model=list[MemoryRecord])
def list_memories(limit:int=Query(100,ge=1,le=100),offset:int=Query(0,ge=0),scope:str|None=None,project_id:str|None=None,kind:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.list(limit=limit,offset=offset,scope=scope,project_id=project_id,kind=kind))
@router.get("/telemetry",response_model=MemoryTelemetry)
def telemetry(manager:MemoryManager=Depends(manager_dep)): return manager.telemetry()
@router.post("/search",response_model=list[SearchResult])
def search(request:MemorySearchRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.search(request))
@router.post("/ingest/text",response_model=MemoryRecord)
def ingest_text(request:IngestTextRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.ingest_text(request))
@router.post("/ingest/file",response_model=MemoryRecord)
def ingest_file(path:str,scope:str="global",project_id:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.ingest_file(path,scope=scope,project_id=project_id))
@router.post("/conversations",response_model=MemoryRecord)
def index_conversation(request:ConversationMemoryRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.index_conversation(request))
@router.post("/reindex")
def reindex(request:ReindexRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.reindex(request.memory_ids or None))
@router.get("/export")
def export_memory(manager:MemoryManager=Depends(manager_dep)): return manager.export_data()
@router.post("/import")
def import_memory(request:ImportRequest,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.import_data(request))
@router.post("/graph/edges",response_model=KnowledgeEdge)
def add_edge(request:KnowledgeEdgeCreate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.add_edge(request))
@router.get("/graph",response_model=list[KnowledgeEdge])
def graph(memory_id:str|None=None,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.graph(memory_id))
@router.get("/{memory_id}",response_model=MemoryRecord)
def get_memory(memory_id:str,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.get(memory_id))
@router.patch("/{memory_id}",response_model=MemoryRecord)
def update_memory(memory_id:str,request:MemoryUpdate,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.update(memory_id,request))
@router.delete("/{memory_id}")
def delete_memory(memory_id:str,manager:MemoryManager=Depends(manager_dep)): return guard(lambda:manager.delete(memory_id))
PY

ok "Memory subsystem generated"

step "Registering memory API router"
"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); text=path.read_text()
import_line="from app.api.memory import router as memory_router"
include_line="app.include_router(memory_router)"
if import_line not in text:
    lines=text.splitlines(); index=0
    for i,line in enumerate(lines):
        if line.startswith("from app.api") or line.startswith("import "): index=i+1
    lines.insert(index,import_line); text="\n".join(lines)+("\n" if path.read_text().endswith("\n") else "")
if include_line not in text:
    root_marker='@app.get("/")'
    if root_marker in text: text=text.replace(root_marker,include_line+"\n\n\n"+root_marker,1)
    else: text += "\n"+include_line+"\n"
path.write_text(text)
PY
ok "Memory API router registered"

step "Updating environment example"
touch "$ROOT/.env.example"
"$PYTHON_BIN" - "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); text=p.read_text()
block='''# Odin Milestone 19 — Long-Term Memory
ODIN_MEMORY_DB=
ODIN_MEMORY_EMBEDDING_PROVIDER=local-hash
ODIN_MEMORY_EMBEDDING_MODEL=odin-hash-v1
ODIN_MEMORY_EMBEDDING_DIMENSIONS=256
ODIN_MEMORY_CHUNK_SIZE=1200
ODIN_MEMORY_CHUNK_OVERLAP=180
ODIN_MEMORY_SEARCH_LIMIT=10
ODIN_MEMORY_SEARCH_MAX_LIMIT=100
ODIN_MEMORY_AUTO_INDEX_CONVERSATIONS=false
'''
if "# Odin Milestone 19" not in text:
    if text and not text.endswith("\n"): text += "\n"
    text += "\n"+block
    p.write_text(text)
PY
ok "Environment example updated"

printf '\n============================================================\nVALIDATING MILESTONE 19\n============================================================\n'
step "Compiling Long-Term Memory subsystem"
"$PYTHON_BIN" -m py_compile "$BACKEND/app/memory/"*.py "$BACKEND/app/api/memory.py"
ok "Memory subsystem syntax passed"

step "Testing persistence, chunking, deduplication, retrieval, graph, import/export, and cleanup"
(
 cd "$BACKEND"; TEST_DB="$(mktemp)"; rm -f "$TEST_DB"
 PYTHONPATH="$BACKEND" ODIN_MEMORY_DB="$TEST_DB" "$PYTHON_BIN" - <<'PY'
from app.memory.manager import MemoryManager
from app.memory.models import *
from app.memory.exceptions import MemoryNotFoundError
m=MemoryManager()
a=m.create(MemoryCreate(title="Odin architecture",content="Odin uses FastAPI for its backend. The agent runtime supports planners, coders, reviewers, debuggers, and researchers.",kind="decision",scope="project",project_id="odin",tags=["architecture","fastapi"]))
assert a.chunk_count >= 1
same=m.create(MemoryCreate(content=a.content,title="duplicate",kind="decision",scope="project",project_id="odin"))
assert same.id==a.id
b=m.create(MemoryCreate(title="Database choice",content="SQLite stores durable metadata and run history. Foreign key cascades protect cleanup integrity.",kind="fact",scope="project",project_id="odin",tags=["database"]))
sem=m.search(MemorySearchRequest(query="FastAPI backend architecture",mode="semantic",project_id="odin",limit=5)); assert sem and sem[0].memory_id==a.id
kw=m.search(MemorySearchRequest(query="foreign key cascades",mode="keyword",project_id="odin",limit=5)); assert kw and kw[0].memory_id==b.id
hy=m.search(MemorySearchRequest(query="agent runtime reviewer",mode="hybrid",project_id="odin",tags=["architecture"])); assert hy and hy[0].memory_id==a.id
updated=m.update(a.id,MemoryUpdate(content=a.content+" Memory provides hybrid retrieval.",tags=["architecture","fastapi","memory"])); assert updated.version==2
edge=m.add_edge(KnowledgeEdgeCreate(source_memory_id=a.id,target_memory_id=b.id,relation="depends_on")); assert m.graph(a.id)[0].id==edge.id
conv=m.index_conversation(ConversationMemoryRequest(conversation_id="c1",project_id="odin",messages=[{"role":"user","content":"Build memory"},{"role":"assistant","content":"Implemented hybrid retrieval"}])); assert conv.kind=="conversation"
exported=m.export_data(); assert len(exported["memories"])==3
re=m.reindex([a.id]); assert re["memories"]==1 and re["chunks"]>=1
tele=m.telemetry(); assert tele.memories==3 and tele.searches==3 and tele.cache_misses>0
m.delete(a.id)
assert m.graph()==[]
with m.store.connect() as db:
 assert db.execute("SELECT COUNT(*) n FROM memory_chunks WHERE memory_id=?",(a.id,)).fetchone()["n"]==0
 assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
try: m.get(a.id); raise AssertionError("deleted memory remained")
except MemoryNotFoundError: pass
print("Memory behavior tests passed")
PY
 rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm"
)
ok "Memory behavior passed"

step "Testing OpenAPI registration"
(
 cd "$BACKEND"; TEST_DB="$(mktemp)"; rm -f "$TEST_DB"
 PYTHONPATH="$BACKEND" ODIN_MEMORY_DB="$TEST_DB" ODIN_AGENTS_DB="$TEST_DB.agents" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from app.main import app
paths=app.openapi()["paths"]
required={"/memory","/memory/telemetry","/memory/search","/memory/ingest/text","/memory/ingest/file","/memory/conversations","/memory/reindex","/memory/export","/memory/import","/memory/graph","/memory/graph/edges","/memory/{memory_id}"}
missing=required-set(paths); assert not missing, f"Missing memory routes: {sorted(missing)}"
print("Memory routes registered")
PY
 rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm" "$TEST_DB.agents" "$TEST_DB.agents-wal" "$TEST_DB.agents-shm"
)
ok "OpenAPI memory routes passed"

step "Testing Memory HTTP endpoints"
(
 cd "$BACKEND"; TEST_DB="$(mktemp)"; rm -f "$TEST_DB"
 PYTHONPATH="$BACKEND" ODIN_MEMORY_DB="$TEST_DB" ODIN_AGENTS_DB="$TEST_DB.agents" ODIN_DEFAULT_PROVIDER=mock "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
 r=c.post("/memory",json={"title":"HTTP memory","content":"Odin remembers software architecture decisions.","kind":"decision","scope":"project","project_id":"odin","tags":["http"]}); assert r.status_code==200,r.text; mid=r.json()["id"]
 assert c.get(f"/memory/{mid}").status_code==200
 s=c.post("/memory/search",json={"query":"architecture decisions","mode":"hybrid","project_id":"odin"}); assert s.status_code==200,s.text; assert s.json()[0]["memory_id"]==mid
 u=c.patch(f"/memory/{mid}",json={"tags":["http","updated"]}); assert u.status_code==200 and "updated" in u.json()["tags"]
 t=c.get("/memory/telemetry"); assert t.status_code==200 and t.json()["memories"]==1
 e=c.get("/memory/export"); assert e.status_code==200 and len(e.json()["memories"])==1
 d=c.delete(f"/memory/{mid}"); assert d.status_code==200
 assert c.get(f"/memory/{mid}").status_code==404
print("Memory HTTP tests passed")
PY
 rm -f "$TEST_DB" "$TEST_DB-wal" "$TEST_DB-shm" "$TEST_DB.agents" "$TEST_DB.agents-wal" "$TEST_DB.agents-shm"
)
ok "Memory HTTP behavior passed"

step "Compiling complete backend"
"$PYTHON_BIN" -m compileall -q "$BACKEND/app"
ok "Complete backend compilation passed"

trap - ERR
printf '\n============================================================\n✅ MILESTONE 19 COMPLETE\n============================================================\n\n'
printf 'Installed:\n  backend/app/memory/\n  backend/app/api/memory.py\n\n'
printf 'Updated:\n  backend/app/main.py\n  .env.example\n\n'
printf 'Capabilities:\n'
printf '  Persistent scoped memories with versioning and deduplication\n'
printf '  Dependency-free deterministic local embeddings\n'
printf '  Semantic, keyword, and hybrid retrieval\n'
printf '  Metadata, project, scope, kind, conversation, and tag filters\n'
printf '  Chunking with overlap and embedding cache\n'
printf '  Text, source file, optional PDF, and conversation ingestion\n'
printf '  Knowledge graph edges with cascading cleanup\n'
printf '  Reindexing, import/export, and telemetry\n'
printf '  SQLite WAL mode, foreign keys, backup, rollback, and idempotent install\n\n'
printf 'Endpoints:\n'
printf '  POST   /memory\n  GET    /memory\n  GET    /memory/{id}\n  PATCH  /memory/{id}\n  DELETE /memory/{id}\n'
printf '  POST   /memory/search\n  POST   /memory/ingest/text\n  POST   /memory/ingest/file\n'
printf '  POST   /memory/conversations\n  POST   /memory/reindex\n  GET    /memory/telemetry\n'
printf '  GET    /memory/export\n  POST   /memory/import\n  GET    /memory/graph\n  POST   /memory/graph/edges\n\n'
printf 'Validation: %s passed, %s skipped\nBackup: %s\n' "$PASS_COUNT" "$SKIP_COUNT" "$BACKUP_DIR"
