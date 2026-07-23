from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from odin_shared.sqlite_persistence import resolve_sqlite_database_path

@dataclass(slots=True)
class MemorySettings:
    database_path: Path = field(default_factory=resolve_sqlite_database_path)
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
    if settings.embedding_dimensions < 32:
        raise ValueError("ODIN_MEMORY_EMBEDDING_DIMENSIONS must be at least 32")
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("Chunk overlap must be smaller than chunk size")
    return settings
