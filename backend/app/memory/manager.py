"""High-level long-term memory manager."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Iterable

from app.memory.models import (
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStats,
)
from app.memory.repository import MemoryRepository
from app.memory.search import MemorySearchEngine
from app.memory.summarizer import ExtractiveSummarizer


class MemoryManager:
    def __init__(
        self,
        repository: MemoryRepository | None = None,
        search_engine: MemorySearchEngine | None = None,
        summarizer: ExtractiveSummarizer | None = None,
    ) -> None:
        self.repository = repository or MemoryRepository()
        self.search_engine = search_engine or MemorySearchEngine()
        self.summarizer = summarizer or ExtractiveSummarizer()
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def store(
        self,
        *,
        content: str,
        kind: MemoryKind = MemoryKind.NOTE,
        title: str = "",
        summary: str | None = None,
        tags: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source: str | None = None,
        project_id: str | None = None,
        context_id: str | None = None,
        job_id: str | None = None,
        importance: float = 0.5,
        auto_summarize: bool = True,
    ) -> MemoryRecord:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Memory content cannot be empty.")

        if summary is None and auto_summarize and len(normalized_content) > 800:
            summary = self.summarizer.summarize(normalized_content)

        record = MemoryRecord(
            kind=kind,
            title=title,
            content=normalized_content,
            summary=summary,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            source=source,
            project_id=project_id,
            context_id=context_id,
            job_id=job_id,
            importance=importance,
        )

        with self._lock:
            return self.repository.save(record)

    def get(self, memory_id: str, *, mark_accessed: bool = True) -> MemoryRecord | None:
        with self._lock:
            record = self.repository.get(memory_id)
            if record is None:
                return None

            if mark_accessed:
                record.accessed_at = self._now()
                record.access_count += 1
                record.updated_at = self._now()
                self.repository.save(record)

            return record

    def update(self, memory_id: str, **changes: Any) -> MemoryRecord:
        with self._lock:
            record = self.repository.get(memory_id)
            if record is None:
                raise KeyError(memory_id)

            protected = {"id", "created_at", "access_count"}
            for key, value in changes.items():
                if key in protected or value is None:
                    continue
                if not hasattr(record, key):
                    raise ValueError(f"Unknown memory field: {key}")
                setattr(record, key, value)

            record.updated_at = self._now()
            validated = MemoryRecord.model_validate(
                record.model_dump(mode="json")
            )
            return self.repository.save(validated)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            return self.repository.delete(memory_id)

    def search(self, request: MemorySearchRequest) -> list[MemorySearchResult]:
        records = self.repository.iter_all()
        return self.search_engine.rank(records, request)

    def summarize_text(
        self,
        text: str,
        *,
        max_sentences: int = 4,
        max_characters: int = 1000,
    ) -> str:
        return self.summarizer.summarize(
            text,
            max_sentences=max_sentences,
            max_characters=max_characters,
        )

    def context_block(
        self,
        query: str,
        *,
        project_id: str | None = None,
        context_id: str | None = None,
        limit: int = 5,
        max_characters: int = 6000,
    ) -> str:
        results = self.search(
            MemorySearchRequest(
                query=query,
                project_id=project_id,
                context_id=context_id,
                limit=limit,
            )
        )

        parts: list[str] = []
        consumed = 0
        for result in results:
            memory = result.memory
            body = memory.summary or memory.content
            block = (
                f"[Memory {memory.id} | {memory.kind.value} | "
                f"score={result.score:.3f}]\n"
                f"{memory.title}\n{body}"
            ).strip()

            if consumed + len(block) > max_characters:
                remaining = max_characters - consumed
                if remaining > 100:
                    parts.append(block[:remaining].rstrip())
                break

            parts.append(block)
            consumed += len(block) + 2

        return "\n\n".join(parts)

    def stats(self) -> MemoryStats:
        return self.repository.stats()


memory_manager = MemoryManager()
