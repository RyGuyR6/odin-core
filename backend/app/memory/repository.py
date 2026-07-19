"""Persistent repository for memory records."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from app.memory.models import MemoryKind, MemoryRecord, MemoryStats
from app.storage.service import storage_service


class MemoryRepository:
    namespace = "memories"

    @property
    def backend(self):
        return storage_service.backend

    def save(self, memory: MemoryRecord) -> MemoryRecord:
        self.backend.put_record(
            self.namespace,
            memory.id,
            memory.model_dump(mode="json"),
        )
        return memory

    def get(self, memory_id: str) -> MemoryRecord | None:
        record = self.backend.get_record(self.namespace, memory_id)
        if record is None:
            return None
        return MemoryRecord.model_validate(record.payload)

    def list(self, *, limit: int = 1000, offset: int = 0) -> list[MemoryRecord]:
        return [
            MemoryRecord.model_validate(record.payload)
            for record in self.backend.list_records(
                self.namespace,
                limit=limit,
                offset=offset,
            )
        ]

    def iter_all(self, *, page_size: int = 500) -> Iterable[MemoryRecord]:
        offset = 0
        while True:
            page = self.list(limit=page_size, offset=offset)
            if not page:
                break
            yield from page
            offset += len(page)
            if len(page) < page_size:
                break

    def delete(self, memory_id: str) -> bool:
        return self.backend.delete_record(self.namespace, memory_id)

    def count(self) -> int:
        return self.backend.count_records(self.namespace)

    def stats(self) -> MemoryStats:
        by_kind: Counter[str] = Counter()
        tags: Counter[str] = Counter()
        importance_total = 0.0
        total = 0

        for memory in self.iter_all():
            total += 1
            by_kind[memory.kind.value] += 1
            tags.update(memory.tags)
            importance_total += memory.importance

        return MemoryStats(
            total=total,
            by_kind=dict(sorted(by_kind.items())),
            top_tags=[
                {"tag": tag, "count": count}
                for tag, count in tags.most_common(20)
            ],
            average_importance=(
                round(importance_total / total, 6)
                if total
                else 0.0
            ),
        )

    def delete_by_kind(self, kind: MemoryKind) -> int:
        deleted = 0
        for memory in self.iter_all():
            if memory.kind == kind and self.delete(memory.id):
                deleted += 1
        return deleted
