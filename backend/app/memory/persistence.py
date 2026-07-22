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
              project_id TEXT, repository_id TEXT, conversation_id TEXT, source TEXT,
              tags_json TEXT NOT NULL DEFAULT '[]',
              metadata_json TEXT NOT NULL DEFAULT '{}', content_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
              importance REAL NOT NULL DEFAULT 0.5, confidence REAL NOT NULL DEFAULT 1.0,
              access_count INTEGER NOT NULL DEFAULT 0, accessed_at TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_hash_scope_project ON memories(content_hash, scope, COALESCE(project_id,''));
            CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_memories_repository ON memories(repository_id);
            CREATE INDEX IF NOT EXISTS idx_memories_conversation ON memories(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
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
            # Apply additive migrations for existing databases
            self._migrate(db)
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(chunk_id UNINDEXED, memory_id UNINDEXED, title, content, tags)")
            except sqlite3.OperationalError:
                pass
    def _migrate(self, db: sqlite3.Connection) -> None:
        """Apply additive schema migrations for previously created databases."""
        cols = {row[1] for row in db.execute("PRAGMA table_info(memories)")}
        additions = [
            ("repository_id", "TEXT"),
            ("importance", "REAL NOT NULL DEFAULT 0.5"),
            ("confidence", "REAL NOT NULL DEFAULT 1.0"),
            ("access_count", "INTEGER NOT NULL DEFAULT 0"),
            ("accessed_at", "TEXT"),
        ]
        for col, col_def in additions:
            if col not in cols:
                db.execute(f"ALTER TABLE memories ADD COLUMN {col} {col_def}")
        # Ensure new indexes exist
        try:
            db.execute("CREATE INDEX IF NOT EXISTS idx_memories_repository ON memories(repository_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC)")
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
