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
    row_keys = set(row.keys())
    return MemoryRecord(
        id=row["id"], title=row["title"], content=row["content"], kind=row["kind"],
        scope=row["scope"], project_id=row["project_id"],
        repository_id=row["repository_id"] if "repository_id" in row_keys else None,
        conversation_id=row["conversation_id"], source=row["source"],
        tags=json.loads(row["tags_json"]), metadata=json.loads(row["metadata_json"]),
        content_hash=row["content_hash"], version=row["version"],
        importance=float(row["importance"]) if "importance" in row_keys and row["importance"] is not None else 0.5,
        confidence=float(row["confidence"]) if "confidence" in row_keys and row["confidence"] is not None else 1.0,
        access_count=int(row["access_count"]) if "access_count" in row_keys and row["access_count"] is not None else 0,
        accessed_at=row["accessed_at"] if "accessed_at" in row_keys else None,
        chunk_count=chunk_count, created_at=row["created_at"], updated_at=row["updated_at"],
    )

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
            db.execute(
                "INSERT INTO memories(id,title,content,kind,scope,project_id,repository_id,conversation_id,source,tags_json,metadata_json,content_hash,version,importance,confidence,access_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (memory_id,request.title,content,request.kind,request.scope,request.project_id,request.repository_id,request.conversation_id,request.source,json.dumps(sorted(set(request.tags))),json.dumps(request.metadata),digest,1,request.importance,request.confidence,0,now,now)
            )
        self._index(memory_id,content); return self.get(memory_id)
    def get(self, memory_id: str) -> MemoryRecord:
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM memories WHERE id=?",(memory_id,)).fetchone()
            if not row: raise MemoryNotFoundError(memory_id)
            count=db.execute("SELECT COUNT(*) n FROM memory_chunks WHERE memory_id=?",(memory_id,)).fetchone()["n"]
        return _record(row,count)
    def list(self, *, limit=100, offset=0, scope=None, project_id=None, repository_id=None, kind=None):
        clauses=[]; params=[]
        for col,val in (("scope",scope),("project_id",project_id),("repository_id",repository_id),("kind",kind)):
            if val is not None: clauses.append(f"{col}=?"); params.append(val)
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        with self.store.connect() as db:
            rows=db.execute(f"SELECT m.*, (SELECT COUNT(*) FROM memory_chunks c WHERE c.memory_id=m.id) chunk_count FROM memories m{where} ORDER BY importance DESC, updated_at DESC LIMIT ? OFFSET ?",(*params,min(limit,self.settings.max_limit),offset)).fetchall()
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
            if not _metadata_matches_extended(row,request): continue
            sem=cosine_similarity(query_vector,json.loads(row["embedding_json"])) if query_vector else 0.0
            kw=keyword_similarity(request.query," ".join([row["title"] or "",row["chunk_content"]," ".join(json.loads(row["tags_json"]))]))
            base_score=combine_scores(sem,kw,request.mode)
            # Blend base score with importance (75% relevance, 25% importance) so
            # high-importance memories rank above equally relevant but lower-importance ones.
            importance=float(row["importance"]) if "importance" in row.keys() and row["importance"] is not None else 0.5
            score=base_score*0.75 + importance*0.25
            if score < request.min_score: continue
            results.append(SearchResult(
                memory_id=row["id"],chunk_id=row["chunk_id"],title=row["title"],content=row["chunk_content"],
                kind=row["kind"],scope=row["scope"],project_id=row["project_id"],
                repository_id=row["repository_id"] if "repository_id" in row.keys() else None,
                source=row["source"],tags=json.loads(row["tags_json"]),
                score=round(score,6),semantic_score=round(max(0,(sem+1)/2),6),keyword_score=round(kw,6),
                importance=round(importance,4),metadata=json.loads(row["metadata_json"]),
            ))
        results.sort(key=lambda x:x.score,reverse=True)
        elapsed=(time.perf_counter()-started)*1000; self.store.metric_inc("searches"); self.store.metric_inc(f"{request.mode}_searches"); self.store.metric_inc("search_ms_total",elapsed)
        return results[:min(request.limit,self.settings.max_limit)]
    def reindex(self, memory_ids: list[str] | None=None):
        records=[self.get(mid) for mid in memory_ids] if memory_ids else self.list(limit=self.settings.max_limit)
        count=0
        for rec in records: count += self._index(rec.id,rec.content)
        return {"memories":len(records),"chunks":count}
    def ingest_text(self, request: IngestTextRequest):
        return self.create(MemoryCreate(
            content=request.text, title=request.title, kind=request.kind, scope=request.scope,
            project_id=request.project_id, repository_id=request.repository_id,
            conversation_id=request.conversation_id, source=request.source,
            tags=request.tags, metadata=request.metadata, importance=request.importance,
        ))
    def ingest_file(self, path: str, *, scope="global",project_id=None,repository_id=None,tags=None):
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
        return self.create(MemoryCreate(content=text,title=p.name,kind=kind,scope=scope,project_id=project_id,repository_id=repository_id,source=str(p),tags=tags or [],metadata={"extension":ext,"size_bytes":p.stat().st_size}))
    def index_conversation(self, request: ConversationMemoryRequest):
        lines=[]
        for msg in request.messages:
            role=str(msg.get("role","unknown")).upper(); content=str(msg.get("content","")).strip()
            if content: lines.append(f"{role}: {content}")
        return self.create(MemoryCreate(content="\n\n".join(lines),title=request.title or f"Conversation {request.conversation_id}",kind="conversation",scope="project" if request.project_id else "conversation",project_id=request.project_id,conversation_id=request.conversation_id,source="conversation",tags=request.tags,metadata={"message_count":len(request.messages)}))
    def record_access(self, memory_id: str):
        """Record an access event for a memory record (increments access_count, updates accessed_at)."""
        now=utcnow()
        with self.store.connect() as db:
            db.execute("UPDATE memories SET access_count=access_count+1,accessed_at=? WHERE id=?",(now,memory_id))
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
            payload=MemoryCreate(content=item["content"],title=item.get("title"),kind=item.get("kind","note"),scope=item.get("scope","global"),project_id=item.get("project_id"),repository_id=item.get("repository_id"),conversation_id=item.get("conversation_id"),source=item.get("source"),tags=item.get("tags",[]),metadata=item.get("metadata",{}),importance=item.get("importance",0.5),confidence=item.get("confidence",1.0),deduplicate=not request.replace_existing)
            if existing and request.replace_existing: self.update(existing.id,MemoryUpdate(content=payload.content,title=payload.title,tags=payload.tags,metadata=payload.metadata,importance=payload.importance,confidence=payload.confidence)); updated+=1
            else: self.create(payload); created+=1
        return {"created":created,"updated":updated}
    def telemetry(self):
        with self.store.connect() as db:
            counts={name:db.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"] for name,table in (("memories","memories"),("chunks","memory_chunks"),("edges","knowledge_edges"),("embedding_cache_entries","embedding_cache"))}
            kind_rows=db.execute("SELECT kind,COUNT(*) n FROM memories GROUP BY kind").fetchall()
            scope_rows=db.execute("SELECT scope,COUNT(*) n FROM memories GROUP BY scope").fetchall()
        by_kind={r["kind"]:r["n"] for r in kind_rows}
        by_scope={r["scope"]:r["n"] for r in scope_rows}
        searches=int(self.store.metric_get("searches")); avg=self.store.metric_get("search_ms_total")/searches if searches else 0.0
        return MemoryTelemetry(**counts,searches=searches,semantic_searches=int(self.store.metric_get("semantic_searches")),keyword_searches=int(self.store.metric_get("keyword_searches")),hybrid_searches=int(self.store.metric_get("hybrid_searches")),cache_hits=int(self.store.metric_get("cache_hits")),cache_misses=int(self.store.metric_get("cache_misses")),average_search_ms=round(avg,3),database_bytes=self.settings.database_path.stat().st_size if self.settings.database_path.exists() else 0,by_kind=by_kind,by_scope=by_scope)

def _metadata_matches_extended(row, request: MemorySearchRequest) -> bool:
    """Extended metadata matching that includes repository_id."""
    if request.scope and row["scope"] != request.scope: return False
    if request.project_id and row["project_id"] != request.project_id: return False
    repo_id = row["repository_id"] if "repository_id" in row.keys() else None
    if request.repository_id and repo_id != request.repository_id: return False
    if request.conversation_id and row["conversation_id"] != request.conversation_id: return False
    if request.kinds and row["kind"] not in request.kinds: return False
    tags=json.loads(row["tags_json"])
    if request.tags and not set(request.tags).issubset(set(tags)): return False
    return True

@lru_cache(maxsize=1)
def get_memory_manager(): return MemoryManager()
